"""Tests for Step 4: Queue-Lag Auto-Scaling (EMA & Cooldown) and Ingestion Backpressure (HTTP 429)."""

from __future__ import annotations

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport

from contracts.events import Event
from contracts.priorities import Priority
from pipeline.dispatcher import (
    DEFAULT_BASE_ALLOCATION,
    DEFAULT_SURGE_ALLOCATION,
    QueueLagAutoScaler,
)
from pipeline.ingestion.api import (
    BackpressureController,
    backpressure_controller,
)
from pipeline.main import app
from pipeline.queues.queue_manager import QueueManager
from pipeline.workers.worker_pool import WorkerPool


# =========================================================================
# 1. EMA Calculation & Dynamic Worker Reallocation Tests
# =========================================================================

def test_ema_depth_calculation_formula():
    """Verify EMA formula: EMA_t = alpha * Depth_t + (1 - alpha) * EMA_{t-1}."""
    scaler = QueueLagAutoScaler(alpha=0.3, sla_threshold=20.0)

    # Initial sample sets EMA_0 = Depth_0
    ema0 = scaler.update_ema(10.0)
    assert ema0 == 10.0

    # Sample 1: EMA_1 = 0.3 * 20.0 + 0.7 * 10.0 = 6.0 + 7.0 = 13.0
    ema1 = scaler.update_ema(20.0)
    assert ema1 == 13.0

    # Sample 2: EMA_2 = 0.3 * 30.0 + 0.7 * 13.0 = 9.0 + 9.1 = 18.1
    ema2 = scaler.update_ema(30.0)
    assert ema2 == 18.1


@pytest.mark.asyncio
async def test_dynamic_reallocation_on_sla_breach():
    """Verify that breaching the SLA threshold shifts workers from NORMAL/BEST_EFFORT strictly to CRITICAL."""
    qm = QueueManager()
    wp = WorkerPool(qm=qm)
    await wp.start(initial_allocation=DEFAULT_BASE_ALLOCATION)

    scaler = QueueLagAutoScaler(
        qm=qm,
        wp=wp,
        sla_threshold=15.0,
        alpha=0.5,
        cooldown_sec=5.0,
        base_allocation=DEFAULT_BASE_ALLOCATION,
        surge_allocation=DEFAULT_SURGE_ALLOCATION,
    )

    try:
        now = 1000.0
        # Initial evaluation under SLA limit
        res1 = await scaler.evaluate_scaling(now=now, critical_depth=10)
        assert res1["action"] == "NONE"
        assert not res1["is_scaled_up"]
        alloc1 = wp.get_allocation()
        assert alloc1[Priority.CRITICAL] == 2
        assert alloc1[Priority.NORMAL] == 4
        assert alloc1[Priority.BEST_EFFORT] == 2

        # Breach SLA threshold: depth = 30 -> EMA = 0.5*30 + 0.5*10 = 20.0 >= 15.0
        res2 = await scaler.evaluate_scaling(now=now + 1.0, critical_depth=30)
        assert res2["action"] == "SCALE_UP"
        assert res2["is_scaled_up"]
        assert scaler.total_scale_ups == 1

        # Verify workers dynamically shifted strictly to CRITICAL
        alloc2 = wp.get_allocation()
        assert alloc2[Priority.CRITICAL] == 6
        assert alloc2[Priority.NORMAL] == 1
        assert alloc2[Priority.BEST_EFFORT] == 1
    finally:
        await wp.stop()


# =========================================================================
# 2. Anti-Thrashing Cooldown Timer Enforcement Tests
# =========================================================================

@pytest.mark.asyncio
async def test_anti_thrashing_cooldown_enforcement():
    """Verify that worker flapping is prevented by enforcing scale-down cooldown timer."""
    qm = QueueManager()
    wp = WorkerPool(qm=qm)
    await wp.start(initial_allocation=DEFAULT_BASE_ALLOCATION)

    scaler = QueueLagAutoScaler(
        qm=qm,
        wp=wp,
        sla_threshold=10.0,
        alpha=1.0,  # immediate tracking for test clarity
        cooldown_sec=5.0,
    )

    try:
        t0 = 1000.0
        # Trigger scale-up at t0
        await scaler.evaluate_scaling(now=t0, critical_depth=20)
        assert scaler.is_scaled_up is True
        assert wp.get_allocation()[Priority.CRITICAL] == 6

        # Traffic drops below SLA at t0 + 2.0s (only 2.0s elapsed < 5.0s cooldown)
        res_cooldown = await scaler.evaluate_scaling(now=t0 + 2.0, critical_depth=0)
        assert res_cooldown["action"] == "COOLDOWN_ACTIVE"
        assert scaler.is_scaled_up is True
        # Critical allocation remains protected at surge capacity
        assert wp.get_allocation()[Priority.CRITICAL] == 6

        # Traffic drops below SLA at t0 + 4.9s (still within 5.0s cooldown)
        res_cooldown_2 = await scaler.evaluate_scaling(now=t0 + 4.9, critical_depth=0)
        assert res_cooldown_2["action"] == "COOLDOWN_ACTIVE"
        assert scaler.is_scaled_up is True

        # At t0 + 5.1s (cooldown satisfied: 5.1s >= 5.0s)
        res_scaled_down = await scaler.evaluate_scaling(now=t0 + 5.1, critical_depth=0)
        assert res_scaled_down["action"] == "SCALE_DOWN"
        assert scaler.is_scaled_up is False
        assert scaler.total_scale_downs == 1

        # Workers restored to base allocation
        base_alloc = wp.get_allocation()
        assert base_alloc[Priority.CRITICAL] == 2
        assert base_alloc[Priority.NORMAL] == 4
        assert base_alloc[Priority.BEST_EFFORT] == 2
    finally:
        await wp.stop()


# =========================================================================
# 3. Ingestion Backpressure (HTTP 429 & Hysteresis) Tests
# =========================================================================

def test_backpressure_watermarks_and_hysteresis():
    """Verify 95% trigger, 80% release hysteresis, and CRITICAL unblocked invariant."""
    controller = BackpressureController(
        high_watermark=0.95,
        low_watermark=0.80,
        total_capacity_override=100,  # 100 capacity for easy percentage arithmetic
    )

    # 1. Below 95%: backpressure inactive
    assert controller.update_state(current_depth=94) is False
    assert controller.should_throttle(Priority.BEST_EFFORT, current_depth=94) is False
    assert controller.should_throttle(Priority.NORMAL, current_depth=94) is False
    assert controller.should_throttle(Priority.CRITICAL, current_depth=94) is False

    # 2. At 95%: backpressure triggered!
    assert controller.update_state(current_depth=95) is True
    assert controller.is_active is True

    # Non-critical traffic is throttled
    assert controller.should_throttle(Priority.BEST_EFFORT, current_depth=95) is True
    assert controller.should_throttle(Priority.NORMAL, current_depth=95) is True

    # Hard Invariant: CRITICAL events are NEVER throttled!
    assert controller.should_throttle(Priority.CRITICAL, current_depth=95) is False
    assert controller.should_throttle(Priority.CRITICAL, current_depth=99) is False

    # 3. Hysteresis: depth drops to 85% (still >= 80% low watermark) -> remains active
    assert controller.update_state(current_depth=85) is True
    assert controller.should_throttle(Priority.BEST_EFFORT, current_depth=85) is True

    # 4. Depth drops below 80% (e.g. 79) -> automatically clears backpressure
    assert controller.update_state(current_depth=79) is False
    assert controller.is_active is False
    assert controller.should_throttle(Priority.BEST_EFFORT, current_depth=79) is False
    assert controller.should_throttle(Priority.NORMAL, current_depth=79) is False


@pytest.mark.asyncio
async def test_http_429_backpressure_api_integration():
    """Integration test: API returns HTTP 429 to non-critical events and 202 to CRITICAL under backpressure."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Override capacity for testing and trigger backpressure
        backpressure_controller.set_capacity_override(100)
        backpressure_controller.set_depth_override(96)  # 96% >= 95%
        assert backpressure_controller.update_state() is True
        assert backpressure_controller.is_active is True

        try:
            # 1. BEST_EFFORT event (CLICK) -> returns HTTP 429
            click_payload = {"event_type": "CLICK", "payload": {"url": "/home"}}
            res_click = await client.post("/events", json=click_payload)
            assert res_click.status_code == 429
            assert "backpressure" in res_click.json()["detail"].lower()

            # 2. NORMAL event (CART_ADD) -> returns HTTP 429
            cart_payload = {"event_type": "CART_ADD", "payload": {"item_id": "i1"}}
            res_cart = await client.post("/events", json=cart_payload)
            assert res_cart.status_code == 429

            # 3. CRITICAL event (ORDER) -> completely UNBLOCKED -> returns 202 Accepted!
            order_payload = {"event_type": "ORDER", "payload": {"amount": 199.0}}
            res_order = await client.post("/events", json=order_payload)
            assert res_order.status_code == 202
            assert res_order.json()["priority"] == "CRITICAL"

            # 4. Clear backpressure (depth drops to 70% < 80%)
            backpressure_controller.set_depth_override(70)
            assert backpressure_controller.update_state() is False
            assert backpressure_controller.is_active is False

            # Non-critical event accepted again
            res_click_restored = await client.post("/events", json=click_payload)
            assert res_click_restored.status_code == 202
        finally:
            backpressure_controller.set_capacity_override(None)
            backpressure_controller.set_depth_override(None)
            backpressure_controller.update_state()
