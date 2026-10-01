from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class TimelineTrack:
    name: str
    color: QColor


DEFAULT_TRACKS = [
    TimelineTrack("Comparison", QColor("#3b82f6")),
    TimelineTrack("Images", QColor("#10b981")),
    TimelineTrack("Text", QColor("#a855f7")),
    TimelineTrack("Audio", QColor("#f59e0b")),
]
