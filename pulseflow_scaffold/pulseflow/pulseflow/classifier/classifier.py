PRIORITY_MAP = {
    "PAYMENT": "CRITICAL",
    "ORDER": "CRITICAL",
    "CART_ADD": "MEDIUM",
    "INVENTORY_UPDATE": "MEDIUM",
    "PAGE_VIEW": "LOW",
    "CLICK": "LOW",
    "LOG": "LOW",
}

def classify(event_type: str) -> str:
    return PRIORITY_MAP.get(event_type.upper(), "LOW")
