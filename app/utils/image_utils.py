from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap


class ImageCache:
    def __init__(self) -> None:
        self._source_cache: dict[str, QPixmap] = {}
        self._scaled_cache: dict[tuple[str, int, int, str], QPixmap] = {}

    def clear(self) -> None:
        self._source_cache.clear()
        self._scaled_cache.clear()

    def pixmap(self, path: str, size: QSize | None = None, fit: str = "contain") -> QPixmap:
        if not path or not Path(path).exists():
            return placeholder_pixmap(size or QSize(320, 220))
        key = str(Path(path).resolve())
        if key not in self._source_cache:
            pixmap = QPixmap(key)
            if pixmap.isNull():
                return placeholder_pixmap(size or QSize(320, 220))
            self._source_cache[key] = pixmap
        pixmap = self._source_cache[key]
        if size is None:
            return pixmap
        scaled_key = (key, size.width(), size.height(), fit)
        if scaled_key not in self._scaled_cache:
            aspect_mode = (
                Qt.AspectRatioMode.KeepAspectRatioByExpanding
                if fit == "cover"
                else Qt.AspectRatioMode.KeepAspectRatio
            )
            scaled = pixmap.scaled(
                size,
                aspect_mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            if fit == "cover":
                left = max(0, (scaled.width() - size.width()) // 2)
                top = max(0, (scaled.height() - size.height()) // 2)
                scaled = scaled.copy(left, top, size.width(), size.height())
            self._scaled_cache[scaled_key] = scaled
        return self._scaled_cache[scaled_key]


def placeholder_pixmap(size: QSize) -> QPixmap:
    width = max(16, size.width())
    height = max(16, size.height())
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#2a3039"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#596273"), 3))
    margin = max(8, min(width, height) // 9)
    painter.drawRoundedRect(margin, margin, width - margin * 2, height - margin * 2, 14, 14)
    painter.drawLine(margin * 2, height - margin * 2, width - margin * 2, margin * 2)
    painter.drawLine(margin * 2, margin * 2, width - margin * 2, height - margin * 2)
    painter.setPen(QColor("#aeb6c2"))
    font = painter.font()
    font.setPointSize(max(9, min(width, height) // 13))
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "IMAGE")
    painter.end()
    return pixmap
