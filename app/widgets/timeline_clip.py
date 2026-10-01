from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect


@dataclass
class PaintedClip:
    item_id: str
    track_name: str
    rect: QRect
