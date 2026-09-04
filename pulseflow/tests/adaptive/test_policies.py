import pytest
from contracts.priorities import Priority
from contracts.actions import Action
from adaptive.pressure.pressure_config import PressureState
from adaptive.policies.policy_engine import PolicyEngine, PolicyDecision

def test_normal_pressure_policies():
    """Test the 3 Priority outcomes under NORMAL pressure."""
    pressure = PressureState.NORMAL
    
    crit = PolicyEngine.decide(Priority.CRITICAL, pressure)
    assert crit.strategy == Action.STREAM
    
    norm = PolicyEngine.decide(Priority.NORMAL, pressure)
    assert norm.strategy == Action.STREAM
    
    best = PolicyEngine.decide(Priority.BEST_EFFORT, pressure)
    assert best.strategy == Action.STREAM


def test_high_pressure_policies():
    """Test the 3 Priority outcomes under HIGH pressure."""
    pressure = PressureState.HIGH
    
    crit = PolicyEngine.decide(Priority.CRITICAL, pressure)
    assert crit.strategy == Action.STREAM
    
    norm = PolicyEngine.decide(Priority.NORMAL, pressure)
    assert norm.strategy == Action.BATCH
    
    best = PolicyEngine.decide(Priority.BEST_EFFORT, pressure)
    assert best.strategy == Action.SAMPLE


def test_extreme_pressure_policies():
    """Test the 3 Priority outcomes under EXTREME pressure."""
    pressure = PressureState.EXTREME
    
    crit = PolicyEngine.decide(Priority.CRITICAL, pressure)
    assert crit.strategy == Action.STREAM
    
    norm = PolicyEngine.decide(Priority.NORMAL, pressure)
    assert norm.strategy == Action.DEFER
    
    best = PolicyEngine.decide(Priority.BEST_EFFORT, pressure)
    assert best.strategy == Action.SHED


def test_decision_structure():
    """Test that the PolicyEngine returns the expected structured data."""
    decision = PolicyEngine.decide(Priority.NORMAL, PressureState.HIGH)
    
    assert isinstance(decision, PolicyDecision)
    assert decision.priority == Priority.NORMAL
    assert decision.pressure == PressureState.HIGH
    assert decision.strategy == Action.BATCH
    assert "micro-batch" in decision.reason.lower()
    assert decision.timestamp > 0
