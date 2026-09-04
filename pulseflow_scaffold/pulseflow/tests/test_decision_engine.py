from pulseflow.decision_engine.policy import decide

def test_critical_is_always_streamed():
    for pressure in [0.1, 0.5, 0.8, 0.99]:
        assert decide("CRITICAL", pressure) == "STREAM"

def test_low_is_shed_at_extreme_pressure():
    assert decide("LOW", 0.95) == "SHED"
