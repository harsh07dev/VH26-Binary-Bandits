"""Tests for PulseFlow pipeline priority classification."""

import pytest
from contracts.priorities import Priority
from contracts.events import Event
from pipeline.classification.priority_classifier import (
    classify,
    classify_event,
    classify_event_type,
)


def test_classify_all_critical_events():
    """Verify all critical event types classify as CRITICAL."""
    assert classify_event_type("ORDER") == Priority.CRITICAL
    assert classify_event_type("PAYMENT") == Priority.CRITICAL
    assert classify("order") == Priority.CRITICAL
    assert classify(" payment ") == Priority.CRITICAL


def test_classify_all_normal_events():
    """Verify all normal event types classify as NORMAL."""
    assert classify_event_type("CART_ADD") == Priority.NORMAL
    assert classify_event_type("INVENTORY_UPDATE") == Priority.NORMAL
    assert classify("cart_add") == Priority.NORMAL
    assert classify("inventory_update") == Priority.NORMAL


def test_classify_all_best_effort_events():
    """Verify all best-effort event types classify as BEST_EFFORT."""
    assert classify_event_type("CLICK") == Priority.BEST_EFFORT
    assert classify_event_type("PAGE_VIEW") == Priority.BEST_EFFORT
    assert classify_event_type("LOG") == Priority.BEST_EFFORT
    assert classify("click") == Priority.BEST_EFFORT
    assert classify("page_view") == Priority.BEST_EFFORT
    assert classify("log") == Priority.BEST_EFFORT


def test_classify_unknown_event_defaults_to_best_effort():
    """Unknown event types should safely default to BEST_EFFORT."""
    assert classify_event_type("UNKNOWN_RANDOM_TYPE") == Priority.BEST_EFFORT
    assert classify("CUSTOM_TELEMETRY") == Priority.BEST_EFFORT


def test_classify_event_object():
    """Verify classify and classify_event work with Event objects."""
    evt = Event(event_type="ORDER", payload={"amount": 100})
    assert evt.priority is None
    p = classify(evt)
    assert p == Priority.CRITICAL
    assert evt.priority == Priority.CRITICAL

    evt_click = Event(event_type="CLICK")
    p2 = classify_event(evt_click)
    assert p2 == Priority.BEST_EFFORT
    assert evt_click.priority == Priority.BEST_EFFORT


def test_classify_invalid_type_raises():
    """Passing non-Event, non-string type raises TypeError."""
    with pytest.raises(TypeError):
        classify(12345)
