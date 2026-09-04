"""Tests for Step 2: Adaptive Priority Aging (Anti-Starvation) and Safety Rules."""

from __future__ import annotations

import asyncio
import time
import pytest

from contracts.events import Event
from contracts.priorities import Priority
from pipeline.dispatcher import (
    Dispatcher,
    is_stateful_event,
    is_stateless_event,
    STATELESS_EVENT_TYPES,
    STATEFUL_EVENT_TYPES,
)
from pipeline.queues.queue_manager import QueueManager


# =========================================================================
# 1. Stateless vs Stateful Safety Classification Tests
# =========================================================================

def test_stateless_and_stateful_event_classification():
    """Verify strictly defined boundaries between stateless and stateful events."""
    for st in ("CLICK", "PAGE_VIEW", "LOG", "click", "log"):
        assert is_stateless_event(st) is True
        assert is_stateful_event(st) is False

    for sf in ("CART_ADD", "INVENTORY_UPDATE", "ORDER", "PAYMENT", "cart_add"):
        assert is_stateful_event(sf) is True
        assert is_stateless_event(sf) is False


# =========================================================================
# 2. Lazy Priority Aging on Normal Pop Tests
# =========================================================================

def test_lazy_priority_aging_promotes_expired_stateless_event():
    """Verify that an expired stateless BEST_EFFORT event is promoted when pulling NORMAL."""
    qm = QueueManager()
    disp = Dispatcher(qm=qm, aging_threshold_sec=5.0)

    now = 1000.0
    # BEST_EFFORT event created 6 seconds ago (expired > 5.0s threshold)
    aged_click = Event(
        event_type="CLICK",
        timestamp=now - 6.0,
        received_at=now - 6.0,
        payload={"url": "/products/123"},
    )
    qm.enqueue_nowait(aged_click, Priority.BEST_EFFORT)

    # NORMAL event created recently
    fresh_cart = Event(
        event_type="CART_ADD",
        timestamp=now - 1.0,
        received_at=now - 1.0,
        payload={"item_id": "item-99"},
    )
    qm.enqueue_nowait(fresh_cart, Priority.NORMAL)

    # Pop from NORMAL lane with current time
    popped = disp.pop_normal_nowait(now=now)

    # Expected: The aged CLICK is promoted to NORMAL and returned first!
    assert popped.event_id == aged_click.event_id
    assert popped.priority == Priority.NORMAL
    assert popped.payload["_aged_from"] == Priority.BEST_EFFORT.value
    assert popped.payload["_promoted_at"] == now
    assert popped.payload["_aging_wait_time"] == 6.0

    # Verify metrics
    assert disp.stats.promoted_count == 1

    # Next pop from NORMAL retrieves the original fresh CART_ADD
    second_popped = disp.pop_normal_nowait(now=now)
    assert second_popped.event_id == fresh_cart.event_id
    assert second_popped.priority == Priority.NORMAL
    assert "_aged_from" not in second_popped.payload


def test_lazy_priority_aging_ignores_unexpired_best_effort():
    """Verify that unexpired BEST_EFFORT events (< threshold) are not promoted."""
    qm = QueueManager()
    disp = Dispatcher(qm=qm, aging_threshold_sec=5.0)

    now = 1000.0
    # BEST_EFFORT created 2 seconds ago (< 5.0s threshold)
    fresh_click = Event(
        event_type="CLICK",
        timestamp=now - 2.0,
        received_at=now - 2.0,
    )
    qm.enqueue_nowait(fresh_click, Priority.BEST_EFFORT)

    fresh_cart = Event(
        event_type="CART_ADD",
        timestamp=now - 1.0,
        received_at=now - 1.0,
    )
    qm.enqueue_nowait(fresh_cart, Priority.NORMAL)

    # Pop from NORMAL lane
    popped = disp.pop_normal_nowait(now=now)

    # Expected: NORMAL event is popped; BEST_EFFORT is not promoted
    assert popped.event_id == fresh_cart.event_id
    assert disp.stats.promoted_count == 0
    assert disp.stats.skipped_not_expired_count == 1

    # BEST_EFFORT queue still contains the click event
    assert qm.best_effort_queue.depth() == 1


# =========================================================================
# 3. Safety Rule: Anti-Causal Inversion for Stateful Events
# =========================================================================

def test_safety_rule_rejects_stateful_event_aging():
    """Safety Rule: Stateful events MUST NEVER undergo priority aging to prevent causal bugs."""
    qm = QueueManager()
    disp = Dispatcher(qm=qm, aging_threshold_sec=5.0)

    now = 1000.0
    # Simulate a stateful event placed in BEST_EFFORT queue that aged > 5.0s
    stale_cart = Event(
        event_type="CART_ADD",
        timestamp=now - 10.0,
        received_at=now - 10.0,
        priority=Priority.BEST_EFFORT,
    )
    qm.best_effort_queue.enqueue_nowait(stale_cart)

    normal_item = Event(
        event_type="INVENTORY_UPDATE",
        timestamp=now - 1.0,
        received_at=now - 1.0,
        priority=Priority.NORMAL,
    )
    qm.normal_queue.enqueue_nowait(normal_item)

    # Pop from NORMAL
    popped = disp.pop_normal_nowait(now=now)

    # Expected: Stateful event in BEST_EFFORT is SKIPPED, normal_item is returned
    assert popped.event_id == normal_item.event_id
    assert disp.stats.promoted_count == 0
    assert disp.stats.skipped_stateful_count == 1

    # Stale stateful event remains in its queue
    assert qm.best_effort_queue.depth() == 1


# =========================================================================
# 4. Critical Lane Invariant & QueueManager Integration
# =========================================================================

@pytest.mark.asyncio
async def test_critical_lane_strictly_unaffected():
    """Verify that CRITICAL lane is strictly isolated and never affected by priority aging."""
    qm = QueueManager()
    disp = Dispatcher(qm=qm, aging_threshold_sec=5.0)

    now = 1000.0
    # Expired click
    qm.best_effort_queue.enqueue_nowait(
        Event(event_type="CLICK", timestamp=now - 10.0, received_at=now - 10.0)
    )

    # Critical payment
    payment = Event(event_type="PAYMENT", timestamp=now - 0.1)
    qm.critical_queue.enqueue_nowait(payment)

    # Pop critical
    popped_crit = await disp.pop_critical()
    assert popped_crit.event_id == payment.event_id
    assert popped_crit.priority == Priority.CRITICAL
    assert disp.stats.promoted_count == 0


@pytest.mark.asyncio
async def test_queue_manager_get_with_aging_integration():
    """Verify QueueManager.get_with_aging seamlessly hooks into Dispatcher."""
    qm = QueueManager()
    now = 500.0

    # Old page view
    old_pv = Event(event_type="PAGE_VIEW", timestamp=now - 8.0, received_at=now - 8.0)
    await qm.enqueue(old_pv, Priority.BEST_EFFORT)

    # Normal cart add
    cart = Event(event_type="CART_ADD", timestamp=now - 0.5)
    await qm.enqueue(cart, Priority.NORMAL)

    # Request NORMAL lane with aging
    event = await qm.get_with_aging(Priority.NORMAL, now=now)
    assert event.event_id == old_pv.event_id
    assert event.priority == Priority.NORMAL
    assert event.payload["_aged_from"] == "BEST_EFFORT"
