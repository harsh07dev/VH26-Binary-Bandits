from dataclasses import dataclass

@dataclass
class Metrics:
    incoming: int = 0
    processed: int = 0
    deferred: int = 0
    shed: int = 0

metrics = Metrics()
