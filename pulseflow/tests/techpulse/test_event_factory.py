"""Unit tests for TechPulse EventFactory."""

import unittest
from techpulse.generator.event_factory import EventFactory
from contracts.events import Event, EventBatch
from contracts.priorities import Priority, EVENT_TYPE_PRIORITY_MAP

class TestEventFactory(unittest.TestCase):

    def test_generation_of_standard_event_types(self):
        factory = EventFactory(seed=42)
        for event_type in EventFactory.STANDARD_TYPES:
            event = factory.create_event(event_type=event_type)
            self.assertIsInstance(event, Event)
            self.assertEqual(event.event_type, event_type)
            self.assertIsInstance(event.payload, dict)
            self.assertIsNone(event.received_at)
            self.assertIsNotNone(event.event_id)
            self.assertGreater(event.timestamp, 0)
            self.assertEqual(event.priority, EVENT_TYPE_PRIORITY_MAP.get(event_type, Priority.BEST_EFFORT))

    def test_default_random_event_creation(self):
        factory = EventFactory(seed=42)
        event = factory.create_event()
        self.assertIsInstance(event, Event)
        self.assertIn(event.event_type, EventFactory.STANDARD_TYPES)

    def test_deterministic_generation(self):
        factory1 = EventFactory(seed=12345)
        factory2 = EventFactory(seed=12345)
        
        event1 = factory1.create_event()
        event2 = factory2.create_event()
        
        self.assertEqual(event1.event_type, event2.event_type)
        self.assertEqual(event1.payload, event2.payload)
        # event_id and timestamp are auto-generated, so we only assert that priority matches
        self.assertEqual(event1.priority, event2.priority)

    def test_batch_generation(self):
        factory = EventFactory(seed=42)
        batch = factory.create_events(count=5)
        
        self.assertIsInstance(batch, EventBatch)
        self.assertEqual(len(batch), 5)
        for event in batch:
            self.assertIsInstance(event, Event)
            self.assertIn(event.event_type, EventFactory.STANDARD_TYPES)

    def test_batch_generation_subset_types(self):
        factory = EventFactory(seed=42)
        subset = ["ORDER", "PAYMENT"]
        batch = factory.create_events(count=10, event_types=subset)
        
        for event in batch:
            self.assertIn(event.event_type, subset)

if __name__ == '__main__':
    unittest.main()
