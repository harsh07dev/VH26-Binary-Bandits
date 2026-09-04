from dataclasses import dataclass

@dataclass
class TrafficProfile:
    events_per_minute: int = 1000

    @property
    def events_per_second(self) -> float:
        return self.events_per_minute / 60

    def spike(self):
        self.events_per_minute *= 20
