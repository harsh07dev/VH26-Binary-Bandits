"""PulseFlow benchmark: Workload generator.

Generates realistic mock e-commerce event streams conforming to PulseFlow contracts.
Supports multi-phase workload simulations:
  - Phase 1: Normal load (~1,000 events/minute)
  - Phase 2: Spike load (e.g., 20x surge to ~20,000 events/minute)
  - Phase 3: Recovery load (returning to normal ~1,000 events/minute)

Also provides asynchronous and synchronous streaming helpers for benchmarks and tests.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Iterator, List, Optional

from contracts.events import Event, EventBatch
from contracts.priorities import Priority, classify_event_type


# Typical realistic e-commerce traffic event mix with weight distribution:
# - Critical (Orders, Payments): ~10%
# - Normal (Cart adds, Inventory updates): ~30%
# - Best-effort (Page views, Clicks, Logs): ~60%
DEFAULT_EVENT_TYPE_DISTRIBUTION: dict[str, float] = {
    "ORDER": 0.05,
    "PAYMENT": 0.05,
    "CART_ADD": 0.20,
    "INVENTORY_UPDATE": 0.10,
    "CLICK": 0.30,
    "PAGE_VIEW": 0.25,
    "LOG": 0.05,
}


def _generate_payload_for_type(event_type: str) -> dict:
    """Generate realistic payload data based on the event type."""
    user_id = f"user_{random.randint(1000, 99999)}"
    item_id = f"item_{random.randint(100, 9999)}"

    if event_type == "ORDER":
        return {
            "user_id": user_id,
            "order_id": f"ord_{uuid.uuid4().hex[:8]}",
            "amount": round(random.uniform(10.0, 500.0), 2),
            "items_count": random.randint(1, 5),
            "payment_method": random.choice(["credit_card", "upi", "paypal"]),
        }
    elif event_type == "PAYMENT":
        return {
            "user_id": user_id,
            "payment_id": f"pay_{uuid.uuid4().hex[:8]}",
            "amount": round(random.uniform(10.0, 500.0), 2),
            "status": "INITIATED",
            "gateway": random.choice(["stripe", "razorpay", "adyen"]),
        }
    elif event_type == "CART_ADD":
        return {
            "user_id": user_id,
            "item_id": item_id,
            "quantity": random.randint(1, 3),
            "price": round(random.uniform(5.0, 150.0), 2),
        }
    elif event_type == "INVENTORY_UPDATE":
        return {
            "item_id": item_id,
            "warehouse_id": f"wh_{random.randint(1, 10)}",
            "stock_delta": random.randint(-5, 50),
        }
    elif event_type == "PAGE_VIEW":
        return {
            "user_id": user_id,
            "url": random.choice(["/home", "/product/flash-sale", "/cart", "/deals", "/categories"]),
            "referrer": random.choice(["google", "direct", "newsletter", "social"]),
        }
    elif event_type == "CLICK":
        return {
            "user_id": user_id,
            "element_id": random.choice(["btn_buy_now", "btn_add_cart", "banner_sale", "nav_item"]),
            "target_url": "/product/detail",
        }
    elif event_type == "LOG":
        return {
            "level": random.choice(["DEBUG", "INFO", "WARN"]),
            "component": random.choice(["frontend_telemetry", "cdn_edge", "auth_proxy"]),
            "message": "client telemetry pulse",
        }
    return {"user_id": user_id, "type": event_type}


def generate_single_event(
    event_type: Optional[str] = None,
    type_distribution: Optional[dict[str, float]] = None,
    priority: Optional[Priority] = None,
    set_priority_eagerly: bool = True,
) -> Event:
    """Generate a single mock Event strictly conforming to contracts.events.Event.
    
    If event_type is not provided, one is sampled according to type_distribution.
    If set_priority_eagerly is True, the priority attribute is set via ensure_priority().
    """
    if event_type is None:
        dist = type_distribution or DEFAULT_EVENT_TYPE_DISTRIBUTION
        types = list(dist.keys())
        weights = list(dist.values())
        event_type = random.choices(types, weights=weights, k=1)[0]

    payload = _generate_payload_for_type(event_type)
    event = Event(
        event_type=event_type,
        payload=payload,
        priority=priority,
    )
    if set_priority_eagerly:
        event.ensure_priority()
    return event


@dataclass
class WorkloadPhase:
    """Configuration for a single phase in the workload."""
    name: str
    rate_events_per_sec: float
    duration_seconds: float

    @property
    def rate_events_per_min(self) -> float:
        return self.rate_events_per_sec * 60.0

    @property
    def total_events_expected(self) -> int:
        return int(self.rate_events_per_sec * self.duration_seconds)


@dataclass
class WorkloadProfile:
    """Multi-phase workload profile representing normal, spike, and recovery phases."""
    phases: list[WorkloadPhase] = field(default_factory=list)
    type_distribution: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_EVENT_TYPE_DISTRIBUTION)
    )

    @classmethod
    def flash_sale(
        cls,
        normal_rate_per_min: float = 1000.0,
        spike_multiplier: float = 20.0,
        normal_duration_sec: float = 10.0,
        spike_duration_sec: float = 15.0,
        recovery_duration_sec: float = 10.0,
    ) -> "WorkloadProfile":
        """Create standard Flash Sale profile: Normal (~1,000/min) -> 20x Spike (~20,000/min) -> Recovery."""
        normal_rate_sec = normal_rate_per_min / 60.0
        spike_rate_sec = (normal_rate_per_min * spike_multiplier) / 60.0

        return cls(
            phases=[
                WorkloadPhase(
                    name="normal",
                    rate_events_per_sec=normal_rate_sec,
                    duration_seconds=normal_duration_sec,
                ),
                WorkloadPhase(
                    name="spike",
                    rate_events_per_sec=spike_rate_sec,
                    duration_seconds=spike_duration_sec,
                ),
                WorkloadPhase(
                    name="recovery",
                    rate_events_per_sec=normal_rate_sec,
                    duration_seconds=recovery_duration_sec,
                ),
            ]
        )

    @classmethod
    def fast_test_profile(
        cls,
        normal_rate_sec: float = 50.0,
        spike_rate_sec: float = 500.0,
        normal_duration_sec: float = 1.0,
        spike_duration_sec: float = 2.0,
        recovery_duration_sec: float = 1.0,
    ) -> "WorkloadProfile":
        """Condensed profile for fast automated testing and CI runs."""
        return cls(
            phases=[
                WorkloadPhase("normal", normal_rate_sec, normal_duration_sec),
                WorkloadPhase("spike", spike_rate_sec, spike_duration_sec),
                WorkloadPhase("recovery", normal_rate_sec, recovery_duration_sec),
            ]
        )

    @property
    def total_duration_seconds(self) -> float:
        return sum(p.duration_seconds for p in self.phases)

    @property
    def total_expected_events(self) -> int:
        return sum(p.total_events_expected for p in self.phases)


class WorkloadGenerator:
    """Generates continuous streams of mock events matching a WorkloadProfile."""

    def __init__(
        self,
        profile: Optional[WorkloadProfile] = None,
        seed: Optional[int] = 42,
    ):
        self.profile = profile or WorkloadProfile.flash_sale()
        if seed is not None:
            random.seed(seed)

    def generate_all_events(self) -> list[Event]:
        """Pre-generate all events across all phases in chronological sequence.
        
        Useful for benchmark runs where identical event sequences are replayed
        across both PulseFlow and Naive FIFO pipelines for fair comparison.
        Each event's payload includes a benchmark metadata tag indicating phase.
        """
        all_events: list[Event] = []
        current_virtual_time = time.time()

        for phase in self.profile.phases:
            count = phase.total_events_expected
            if count <= 0:
                continue
            interval = phase.duration_seconds / count
            for i in range(count):
                event = generate_single_event(
                    type_distribution=self.profile.type_distribution,
                    set_priority_eagerly=True,
                )
                event.timestamp = current_virtual_time + (i * interval)
                event.payload["_benchmark_phase"] = phase.name
                all_events.append(event)
            current_virtual_time += phase.duration_seconds

        return all_events

    async def stream_events_async(
        self,
        time_dilation: float = 1.0,
    ) -> AsyncIterator[tuple[Event, str]]:
        """Asynchronously stream events at the configured rates per phase.
        
        Yields (Event, phase_name).
        time_dilation > 1.0 accelerates playback (e.g. 10.0 runs 10x faster).
        """
        for phase in self.profile.phases:
            count = phase.total_events_expected
            if count <= 0:
                continue

            interval = (1.0 / phase.rate_events_per_sec) / time_dilation
            for _ in range(count):
                event = generate_single_event(
                    type_distribution=self.profile.type_distribution,
                    set_priority_eagerly=True,
                )
                event.payload["_benchmark_phase"] = phase.name
                yield event, phase.name
                if interval > 0.0001:
                    await asyncio.sleep(interval)