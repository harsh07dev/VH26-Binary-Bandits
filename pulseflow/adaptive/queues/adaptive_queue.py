"""PulseFlow adaptive: Adaptive Queue Router.

Integrates the AdaptiveClassifier with the existing QueueManager to provide
intelligent, priority-aware routing of events into logically isolated queues.
"""

from contracts.events import Event
from contracts.priorities import Priority
from adaptive.classification.classifier import AdaptiveClassifier
from pipeline.queues.queue_manager import queue_manager

class AdaptiveQueueRouter:
    """Routes events into the appropriate priority queue based on classification."""
    
    @classmethod
    async def route_event(cls, event: Event) -> None:
        """Classify and enqueue an event asynchronously."""
        classification = AdaptiveClassifier.classify(event)
        await queue_manager.enqueue(event, priority=classification.assigned_priority)
        
    @classmethod
    def route_event_nowait(cls, event: Event) -> None:
        """Classify and enqueue an event synchronously."""
        classification = AdaptiveClassifier.classify(event)
        queue_manager.enqueue_nowait(event, priority=classification.assigned_priority)
        
    @classmethod
    def get_metrics(cls) -> dict:
        """Expose queue depths for the adaptive scheduler."""
        metrics = queue_manager.queue_metrics()
        return {
            "criticalQueueDepth": metrics.critical,
            "normalQueueDepth": metrics.normal,
            "bestEffortQueueDepth": metrics.best_effort
        }

    @classmethod
    async def dequeue(cls, priority: Priority) -> Event:
        """Dequeue an event from a specific priority lane."""
        return await queue_manager.get(priority)
        
    @classmethod
    def dequeue_nowait(cls, priority: Priority) -> Event:
        """Dequeue an event synchronously from a specific priority lane."""
        return queue_manager.get_nowait(priority)

    @classmethod
    def clear_all(cls) -> None:
        """Utility to clear all queues (useful for testing)."""
        queue_manager.clear()
