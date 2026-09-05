"""Tests for PulseFlow backend telemetry: RateTracker and GET /metrics/adaptive."""

import asyncio
import time
import pytest
from httpx import AsyncClient, ASGITransport

from pipeline.main import app, lifespan, RateTracker, rate_tracker
from contracts.priorities import Priority
from adaptive.scheduler.metrics_tracker import adaptive_metrics
from adaptive.scheduler.decision_engine import AdaptiveDecision
from contracts.actions import Action
from adaptive.pressure.pressure_config import PressureState


class TestRateTracker:
    """Unit tests for the RateTracker sliding-window telemetry component."""

    def test_initial_state(self):
        tracker = RateTracker(window_sec=1.0)
        assert tracker.get_rate() == 0.0
        assert tracker.current_rate == 0.0
        assert tracker.total_count == 0

    def test_mark_and_rate_calculation(self):
        tracker = RateTracker(window_sec=1.0)
        t0 = 1000.0

        # Mark 10 events at t0
        for _ in range(10):
            rate = tracker.mark(now=t0)
        
        assert tracker.total_count == 10
        # 10 events in window <= 1.0s -> 10.0 events/sec
        assert tracker.get_rate(now=t0) == 10.0

        # Mark 10 more events at t0 + 0.5s
        t1 = t0 + 0.5
        for _ in range(10):
            tracker.mark(now=t1)
        
        assert tracker.total_count == 20
        # 20 events in window <= 1.0s -> 20.0 events/sec
        assert tracker.get_rate(now=t1) == 20.0

    def test_sliding_window_pruning_and_decay(self):
        tracker = RateTracker(window_sec=1.0)
        t0 = 1000.0

        # Mark 5 events at t0
        for _ in range(5):
            tracker.mark(now=t0)

        assert tracker.get_rate(now=t0) == 5.0

        # At t0 + 0.5s, mark 5 events
        t1 = t0 + 0.5
        for _ in range(5):
            tracker.mark(now=t1)

        assert tracker.get_rate(now=t1) == 10.0

        # At t0 + 1.2s, the first 5 events (at t0) have aged out of the 1.0s window
        t2 = t0 + 1.2
        assert tracker.get_rate(now=t2) == 5.0

        # At t0 + 2.0s, all events have aged out
        t3 = t0 + 2.0
        assert tracker.get_rate(now=t3) == 0.0

    def test_reset(self):
        tracker = RateTracker(window_sec=1.0)
        tracker.mark()
        tracker.mark()
        assert tracker.total_count == 2
        tracker.reset()
        assert tracker.total_count == 0
        assert tracker.get_rate() == 0.0


@pytest.mark.asyncio
class TestAdaptiveTelemetryEndpoint:
    """Integration tests for GET /metrics/adaptive endpoint telemetry."""

    async def test_adaptive_metrics_structure_and_initial_rate(self):
        rate_tracker.reset()
        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                res = await client.get("/metrics/adaptive")
                assert res.status_code == 200
                data = res.json()

                # Verify top-level structure
                assert "metrics" in data
                assert "infraMetrics" in data
                assert "shedStats" in data
                assert "recentEvents" in data

                # Verify infraMetrics fields including totalWorkers
                assert "totalWorkers" in data["infraMetrics"]
                assert data["infraMetrics"]["totalWorkers"] > 0

                # Verify actual ingress rate fields
                assert "actual_ingress_rate" in data
                assert "ingress_rate" in data
                assert "ingressRate" in data
                assert data["actual_ingress_rate"] == 0.0

                metrics = data["metrics"]
                # Ingress must match actual ingress rate, not pressureScore
                assert metrics["ingress"] == 0.0
                assert metrics["actual_ingress_rate"] == 0.0
                assert metrics["ingressRate"] == 0.0
                assert metrics["ingress_rate"] == 0.0

                # Verify required existing fields are present
                assert "queueSize" in metrics
                assert "latency" in metrics
                assert "workerLoad" in metrics
                assert "processingCost" in metrics
                assert "isSpikeMode" in metrics
                assert "throughput" in metrics
                assert "pressureState" in metrics
                assert "pressureScore" in metrics

    async def test_ingress_rate_not_calculated_from_pressure_score(self):
        """Explicitly verify that ingress is NOT computed as pressure_score * 1000."""
        rate_tracker.reset()

        # Set a mock decision with high pressure score
        mock_decision = AdaptiveDecision(
            event_id="test-event-001",
            priority=Priority.CRITICAL,
            pressure_state=PressureState.EXTREME,
            pressure_score=0.95,
            strategy=Action.STREAM,
            queue_depth=50,
            worker_allocation={Priority.CRITICAL: 4, Priority.NORMAL: 3, Priority.BEST_EFFORT: 1},
            decision_reason="Extreme pressure test",
        )
        orig_decision = adaptive_metrics.latest_decision
        adaptive_metrics.record_decision(mock_decision)

        try:
            # Mark 15 events into rate_tracker
            for _ in range(15):
                rate_tracker.mark()

            actual_rate = rate_tracker.get_rate()
            assert actual_rate > 0.0

            async with lifespan(app):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as client:
                    res = await client.get("/metrics/adaptive")
                    assert res.status_code == 200
                    data = res.json()

                    metrics = data["metrics"]
                    # If calculated from pressureScore, ingress would be 0.95 * 1000 = 950.0
                    assert metrics["pressureScore"] == 0.95
                    assert metrics["ingress"] != 950.0
                    # It MUST be the actual rate from RateTracker
                    assert metrics["ingress"] == actual_rate
                    assert metrics["actual_ingress_rate"] == actual_rate
                    assert data["actual_ingress_rate"] == actual_rate
        finally:
            adaptive_metrics.latest_decision = orig_decision
            rate_tracker.reset()

    async def test_ingress_tracking_via_event_ingestion(self):
        """Verify that ingesting events updates RateTracker and GET /metrics/adaptive."""
        rate_tracker.reset()

        async with lifespan(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Ingest 5 events
                for i in range(5):
                    res = await client.post(
                        "/events",
                        json={
                            "event_id": f"telemetry-evt-{i}",
                            "event_type": "CLICK",
                            "payload": {"click_idx": i},
                        },
                    )
                    assert res.status_code == 202

                # Query adaptive metrics
                res_metrics = await client.get("/metrics/adaptive")
                assert res_metrics.status_code == 200
                data = res_metrics.json()

                assert rate_tracker.total_count >= 5
                assert data["metrics"]["actual_ingress_rate"] > 0.0
                assert data["metrics"]["ingress"] == data["metrics"]["actual_ingress_rate"]
                assert data["actual_ingress_rate"] == data["metrics"]["actual_ingress_rate"]
