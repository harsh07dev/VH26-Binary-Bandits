import uuid
from datetime import datetime, timezone
import random

EVENT_TYPES = [
    "PAGE_VIEW",
    "CLICK",
    "CART_ADD",
    "INVENTORY_UPDATE",
    "ORDER",
    "PAYMENT",
]

def create_event():
    event_type = random.choices(
        EVENT_TYPES,
        weights=[45, 25, 10, 5, 7, 8],
        k=1,
    )[0]

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"source": "techpulse", "product_id": random.randint(1, 100)},
    }
