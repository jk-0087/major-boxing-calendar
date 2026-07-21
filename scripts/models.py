from __future__ import annotations
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class DiscoveredEvent:
    title: str
    event_date: date
    source_url: str
    broadcaster: str = "DAZN"

    @property
    def fighters(self) -> tuple[str, str]:
        left, right = self.title.split(" vs ", 1)
        return left.strip(), right.strip()
