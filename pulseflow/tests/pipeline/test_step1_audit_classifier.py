"""Tests for Step 1: Decision Lineage, Dynamic Scoring, and Async SQLite Audit Logging."""

from __future__ import annotations

import asyncio
import time
import pytest
from contracts.events import Event
from contracts.priorities import Priority
from pipeline.audit import AuditLogger
from pipeline.classifier import (
    DEFAULT_BASE_PRIORITY_WEIGHTS,
    calculate_dynamic_score,
    classify,
    classify_with_lineage,
)


# =========================================================================
# 1. Event Audit Lineage Contract Tests
# =========================================================================

def test_event_payload_audit_attachment():
    """Verify Event.payload is properly enriched with _audit metadata."""
    event = Event(event_type="ORDER", payload={"amount": 499.0})
    assert event.audit is None

    audit_meta = event.attach_audit(
        rule_id="rule-test-order",
        score=105.25,
        evaluated_at=1700000000.0,
        features={"tier": "vip", "backlog": 12},
    )

    assert "_audit" in event.payload
    assert event.audit == audit_meta
    assert event.payload["_audit"]["rule_id"] == "rule-test-order"
    assert event.payload["_audit"]["score"] == 105.25
    assert event.payload["_audit"]["evaluated_at"] == 1700000000.0
    assert event.payload["_audit"]["features"] == {"tier": "vip", "backlog": 12}
    # Ensure original payload data is preserved
    assert event.payload["amount"] == 499.0


# =========================================================================
# 2. Dynamic Priority Scoring Tests: Score = (w1*Base) + (w2*Wait) + (w3*Queue)
# =========================================================================

def test_dynamic_scoring_formula():
    """Verify exact calculation of dynamic score formula."""
    now = 1000.0
    event = Event(event_type="ORDER", timestamp=998.0)  # Wait time = 2.0s
    event.ensure_priority()

    # Base priority for CRITICAL = 100.0
    # w1 = 1.0, w2 = 2.0, w3 = 0.5
    # Score = (1.0 * 100.0) + (2.0 * 2.0) + (0.5 * 10) = 100 + 4 + 5 = 109.0
    score = calculate_dynamic_score(
        event=event,
        queue_depth=10,
        current_time=now,
        w1=1.0,
        w2=2.0,
        w3=0.5,
    )
    assert score == 109.0


def test_dynamic_scoring_custom_weights():
    """Verify dynamic scoring respects custom weights and tiers."""
    now = 500.0
    event_click = Event(event_type="CLICK", timestamp=490.0)  # Wait time = 10.0s
    # Base priority for BEST_EFFORT = 10.0
    # w1 = 2.0, w2 = 1.5, w3 = 0.2, queue_depth = 50
    # Score = (2.0 * 10.0) + (1.5 * 10.0) + (0.2 * 50) = 20 + 15 + 10 = 45.0
    score = calculate_dynamic_score(
        event=event_click,
        queue_depth=50,
        current_time=now,
        w1=2.0,
        w2=1.5,
        w3=0.2,
    )
    assert score == 45.0


def test_classify_with_lineage_enriches_event():
    """Verify classify_with_lineage assigns priority, computes score, and attaches audit dictionary."""
    event = Event(event_type="PAYMENT", payload={"gateway": "stripe"})
    p, score, audit_data = classify_with_lineage(
        event=event,
        queue_depth=5,
        current_time=event.timestamp + 1.0,
    )

    assert p == Priority.CRITICAL
    assert event.priority == Priority.CRITICAL
    assert score > 100.0
    assert event.audit is not None
    assert event.audit["rule_id"] == "rule-dynamic-critical"
    assert event.audit["score"] == score
    assert event.audit["features"]["base_priority"] == "CRITICAL"
    assert event.audit["features"]["queue_depth"] == 5


# =========================================================================
# 3. Embedded SQLite in WAL Mode & Async Batch Logger Tests
# =========================================================================

@pytest.mark.asyncio
async def test_audit_logger_wal_mode(tmp_path):
    """Verify SQLite initializes in WAL (Write-Ahead Logging) journal mode."""
    test_db = str(tmp_path / "test_audit_wal.db")
    logger = AuditLogger(db_path=test_db)
    await logger.start()

    try:
        journal_mode = logger.get_journal_mode()
        assert journal_mode == "wal", f"Expected WAL mode, got {journal_mode}"
    finally:
        await logger.stop()


@pytest.mark.asyncio
async def test_audit_logger_batch_flushing(tmp_path):
    """Verify single-threaded worker flushes records in batches via executemany."""
    test_db = str(tmp_path / "test_audit_batch.db")
    # Batch size 50, flush interval 100ms
    logger = AuditLogger(db_path=test_db, batch_size=50, flush_interval_ms=100.0)
    await logger.start()

    try:
        events = []
        for i in range(120):
            e = Event(event_type="ORDER" if i % 2 == 0 else "CLICK")
            classify_with_lineage(e, queue_depth=i)
            events.append(e)
            logger.log_event_nowait(e)

        # Allow worker loop to collect and batch-flush
        await asyncio.sleep(0.3)

        count = await logger.count_logs()
        assert count == 120, f"Expected 120 logged records, found {count}"

        # Verify a specific record
        sample = events[0]
        logs = await logger.get_logs_for_event(sample.event_id)
        assert len(logs) == 1
        assert logs[0]["event_id"] == sample.event_id
        assert logs[0]["event_type"] == "ORDER"
        assert logs[0]["priority"] == "CRITICAL"
        assert logs[0]["score"] > 0
    finally:
        await logger.stop()


@pytest.mark.asyncio
async def test_audit_logger_parallel_concurrency_no_locking_errors(tmp_path):
    """Verify concurrent async producers write to SQLite without database-is-locked errors."""
    test_db = str(tmp_path / "test_audit_parallel.db")
    logger = AuditLogger(db_path=test_db, batch_size=25, flush_interval_ms=50.0)
    await logger.start()

    try:
        async def producer(producer_id: int, count: int):
            for j in range(count):
                evt = Event(event_type="PAYMENT", payload={"producer": producer_id, "seq": j})
                classify_with_lineage(evt, queue_depth=j)
                await logger.log_event(evt)

        # Spawn 20 parallel producers logging 15 events each = 300 events
        tasks = [producer(pid, 15) for pid in range(20)]
        await asyncio.gather(*tasks)

        # Flush remaining and assert count
        await logger.flush()
        count = await logger.count_logs()
        assert count == 300, f"Expected 300 records under parallel load, got {count}"
    finally:
        await logger.stop()
