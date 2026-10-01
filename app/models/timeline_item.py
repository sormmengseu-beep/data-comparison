from __future__ import annotations

from dataclasses import asdict, dataclass, field
from uuid import uuid4


@dataclass
class TimelineItem:
    track: str
    name: str
    start_time: float
    duration: float
    source_id: str = ""
    id: str = field(default_factory=lambda: f"clip_{uuid4().hex[:8]}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineItem":
        return cls(
            id=str(data.get("id") or f"clip_{uuid4().hex[:8]}"),
            track=str(data.get("track") or "Comparison"),
            name=str(data.get("name") or "Clip"),
            start_time=max(0.0, float(data.get("start_time") or 0.0)),
            duration=max(0.1, float(data.get("duration") or 0.1)),
            source_id=str(data.get("source_id") or ""),
        )
