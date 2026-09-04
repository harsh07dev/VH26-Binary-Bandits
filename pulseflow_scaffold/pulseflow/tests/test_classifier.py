from pulseflow.classifier.classifier import classify

def test_critical_events():
    assert classify("ORDER") == "CRITICAL"
    assert classify("PAYMENT") == "CRITICAL"

def test_medium_events():
    assert classify("CART_ADD") == "MEDIUM"
    assert classify("INVENTORY_UPDATE") == "MEDIUM"

def test_low_events():
    assert classify("PAGE_VIEW") == "LOW"
    assert classify("CLICK") == "LOW"
