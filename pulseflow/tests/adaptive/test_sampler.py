"""Tests for the Probabilistic Sampler."""

import pytest
from contracts.events import Event
from adaptive.sampling.sampler import ProbabilisticSampler


def test_sampler_initialization_defaults():
    sampler = ProbabilisticSampler()
    assert 0.0 <= sampler.get_sample_rate() <= 1.0
    assert sampler.total_evaluated == 0
    assert sampler.kept_count == 0
    assert sampler.dropped_count == 0


def test_sampler_invalid_rates():
    with pytest.raises(ValueError):
        ProbabilisticSampler(sample_rate=-0.1)

    with pytest.raises(ValueError):
        ProbabilisticSampler(sample_rate=1.1)

    sampler = ProbabilisticSampler(sample_rate=0.5)
    with pytest.raises(ValueError):
        sampler.set_sample_rate(2.0)


def test_sampler_rate_zero_drops_all():
    sampler = ProbabilisticSampler(sample_rate=0.0)
    event = Event(event_type="CLICK")

    for _ in range(50):
        decision = sampler.should_keep(event)
        assert decision is False

    assert sampler.total_evaluated == 50
    assert sampler.kept_count == 0
    assert sampler.dropped_count == 50


def test_sampler_rate_one_keeps_all():
    sampler = ProbabilisticSampler(sample_rate=1.0)
    event = Event(event_type="LOG")

    for _ in range(50):
        decision = sampler.should_keep(event)
        assert decision is True

    assert sampler.total_evaluated == 50
    assert sampler.kept_count == 50
    assert sampler.dropped_count == 0


def test_sampler_probabilistic_distribution():
    # Deterministic test with seed
    sampler = ProbabilisticSampler(sample_rate=0.5, seed=42)
    event = Event(event_type="PAGE_VIEW")

    for _ in range(1000):
        sampler.should_keep(event)

    assert sampler.total_evaluated == 1000
    # Over 1000 iterations at 0.5, kept count will be very close to 500
    assert 430 <= sampler.kept_count <= 570
    assert sampler.kept_count + sampler.dropped_count == 1000


def test_sampler_reset_metrics():
    sampler = ProbabilisticSampler(sample_rate=0.5, seed=123)
    event = Event(event_type="CLICK")
    for _ in range(10):
        sampler.should_keep(event)

    assert sampler.total_evaluated == 10
    sampler.reset_metrics()
    assert sampler.total_evaluated == 0
    assert sampler.kept_count == 0
    assert sampler.dropped_count == 0
