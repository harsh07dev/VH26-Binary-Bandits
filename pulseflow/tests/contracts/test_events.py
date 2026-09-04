"""Unit tests for PulseFlow contracts: Events and Priorities."""

import pytest
from contracts.priorities import Priority, classify_event_type, EVENT_TYPE_PRIORITY_MAP
from contracts.events import Event, EventBatch


def test_priority_enum_values():
    assert Priority.CRITICAL.value == "CRITICAL"
    assert Priority.NORMAL.value == "NORMAL"
    assert Priority.BEST_EFFORT.value == "BEST_EFFORT"


def test_priority_from_str():
    assert Priority.from_str("CRITICAL") == Priority.CRITICAL
    assert Priority.from_str("critical") == Priority.CRITICAL
    assert Priority.from_str("NORMAL") == Priority.NORMAL
    assert Priority.from_str("normal") == Priority.NORMAL
    assert Priority.from_str("BEST_EFFORT") == Priority.BEST_EFFORT
    assert Priority.from_str("best-effort") == Priority.BEST_EFFORT
    assert Priority.from_str("BEST-EFFORT") == Priority.BEST_EFFORT

    with pytest.raises(ValueError):
        Priority.from_str("INVALID_PRIORITY")


def test_event_classification():
    assert classify_event_type("ORDER") == Priority.CRITICAL
    assert classify_event_type("PAYMENT") == Priority.CRITICAL
    assert classify_event_type("CART_ADD") == Priority.NORMAL
    assert classify_event_type("INVENTORY_UPDATE") == Priority.NORMAL
    assert classify_event_type("CLICK") == Priority.BEST_EFFORT
    assert classify_event_type("PAGE_VIEW") == Priority.BEST_EFFORT
    assert classify_event_type("LOG") == Priority.BEST_EFFORT
    assert classify_event_type("UNKNOWN_CUSTOM") == Priority.BEST_EFFORT


def test_event_creation_and_defaults():
    event = Event(event_type="ORDER", payload={"amount": 99.99, "user_id": "u1"})
    assert event.event_id is not None
    assert len(event.event_id) > 0
    assert event.event_type == "ORDER"
    assert event.timestamp > 0
    assert event.payload["amount"] == 99.99
    assert event.priority is None

    # Priority assignment via ensure_priority
    p = event.ensure_priority()
    assert p == Priority.CRITICAL
    assert event.priority == Priority.CRITICAL


def test_event_batch():
    e1 = Event(event_type="ORDER")
    e2 = Event(event_type="CLICK")
    batch = EventBatch(events=[e1, e2])

    assert len(batch) == 2
    items = list(batch)
    assert items[0].event_type == "ORDER"
    assert items[1].event_type == "CLICK"


def test_event_serialization():
    event = Event(event_type="PAYMENT", payload={"order_id": "123"})
    json_str = event.model_dump_json()
    restored = Event.model_validate_json(json_str)

    assert restored.event_id == event.event_id
    assert restored.event_type == "PAYMENT"
    assert restored.payload == {"order_id": "123"}
