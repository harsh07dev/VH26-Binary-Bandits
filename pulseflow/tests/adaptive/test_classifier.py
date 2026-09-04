import pytest
from contracts.events import Event
from contracts.priorities import Priority
from adaptive.classification.classifier import AdaptiveClassifier, ClassificationResult

def test_critical_classification():
    event = Event(event_type="ORDER")
    result = AdaptiveClassifier.classify(event)
    
    assert isinstance(result, ClassificationResult)
    assert result.event_id == event.event_id
    assert result.event_type == "ORDER"
    assert result.assigned_priority == Priority.CRITICAL
    assert "Explicitly mapped" in result.reason
    assert event.priority == Priority.CRITICAL

def test_normal_classification():
    event = Event(event_type="CART_ADD")
    result = AdaptiveClassifier.classify(event)
    
    assert result.assigned_priority == Priority.NORMAL
    assert "Explicitly mapped" in result.reason
    assert event.priority == Priority.NORMAL

def test_best_effort_classification():
    event = Event(event_type="CLICK")
    result = AdaptiveClassifier.classify(event)
    
    assert result.assigned_priority == Priority.BEST_EFFORT
    assert "Explicitly mapped" in result.reason
    assert event.priority == Priority.BEST_EFFORT

def test_unmapped_event_defaults_to_best_effort():
    event = Event(event_type="UNKNOWN_EVENT")
    result = AdaptiveClassifier.classify(event)
    
    assert result.assigned_priority == Priority.BEST_EFFORT
    assert "defaults to" in result.reason
    assert "UNKNOWN_EVENT" in result.reason
    assert event.priority == Priority.BEST_EFFORT

def test_case_insensitivity():
    event = Event(event_type="PaYmEnT")
    result = AdaptiveClassifier.classify(event)
    
    assert result.assigned_priority == Priority.CRITICAL
    assert "PAYMENT" in result.reason
    assert event.priority == Priority.CRITICAL
