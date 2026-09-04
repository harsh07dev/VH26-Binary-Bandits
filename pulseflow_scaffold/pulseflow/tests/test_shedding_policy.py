from pulseflow.backpressure.shedding_policy import can_shed

def test_critical_cannot_be_shed():
    assert can_shed("CRITICAL") is False

def test_low_can_be_shed():
    assert can_shed("LOW") is True
