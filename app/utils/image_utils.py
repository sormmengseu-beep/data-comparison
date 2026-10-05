from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRect, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from app.models.comparison_item import normalize_image_transform


def image_field_frame_size(
    fields: list[dict[str, str]],
    field_id: str,
    field_styles: dict[str, dict[str, str]],
    card_size: QSize,
    image_height_percent: int,
) -> QSize:
    """Return the actual rendered image-object size for the crop editor frame."""
    card_width = max(1, card_size.width())
    card_height = max(1, card_size.height())
    style = field_styles.get(field_id, {})
    geometry_keys = ("overlay_x", "overlay_y", "overlay_width", "overlay_height")
    if all(style.get(key, "") not in (None, "") for key in geometry_keys):
        try:
            x = max(0, min(1000, int(style["overlay_x"])))
            y = max(0, min(1000, int(style["overlay_y"])))
            width = min(max(20, min(1000, int(style["overlay_width"]))), 1000 - x)
            height = min(max(20, min(1000, int(style["overlay_height"]))), 1000 - y)
            return QSize(
                max(1, round(card_width * width / 1000)),
                max(1, round(card_height * height / 1000)),
            )
        except (TypeError, ValueError):
            pass

    image_fields = [field for field in fields if field.get("type") == "image"]
    if not image_fields:
        return QSize(card_width, card_height)
    total_height = card_height
    if len(image_fields) != len(fields):
        total_height = round(card_height * max(0, min(100, image_height_percent)) / 100)
    weights = []
    for field in image_fields:
        image_id = str(field.get("id", ""))
        try:
            weight = int(field_styles.get(image_id, {}).get("height_weight", 100))
        except (TypeError, ValueError):
            weight = 100
        weights.append(max(25, min(400, weight)))
    remaining_pixels = total_height
    remaining_weight = sum(weights)
    for index, field in enumerate(image_fields):
        row_height = (
            remaining_pixels
            if index == len(image_fields) - 1
            else max(1, round(remaining_pixels * weights[index] / max(1, remaining_weight)))
        )
        if str(field.get("id", "")) == field_id:
            return QSize(card_width, max(1, row_height))
        remaining_pixels -= row_height
        remaining_weight -= weights[index]
    return QSize(card_width, max(1, total_height // len(image_fields)))


class ImageCache:
    def __init__(self) -> None:
        self._source_cache: dict[str, QPixmap] = {}
        self._scaled_cache: dict[tuple[str, int, int, str, float, float], QPixmap] = {}

    def clear(self) -> None:
        self._source_cache.clear()
        self._scaled_cache.clear()

    def pixmap(
        self,
        path: str,
        size: QSize | None = None,
        fit: str = "contain",
        crop_x: float = 0.0,
        crop_y: float = 0.0,
    ) -> QPixmap:
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
        crop_x = max(-1.0, min(1.0, float(crop_x)))
        crop_y = max(-1.0, min(1.0, float(crop_y)))
        scaled_key = (
            key,
            size.width(),
            size.height(),
            fit,
            round(crop_x, 3),
            round(crop_y, 3),
        )
        if scaled_key not in self._scaled_cache:
            if fit == "stretch":
                aspect_mode = Qt.AspectRatioMode.IgnoreAspectRatio
            elif fit == "cover":
                aspect_mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding
            else:
                aspect_mode = Qt.AspectRatioMode.KeepAspectRatio
            scaled = pixmap.scaled(
                size,
                aspect_mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            if fit == "cover":
                extra_width = max(0, scaled.width() - size.width())
                extra_height = max(0, scaled.height() - size.height())
                left = int(round(extra_width * ((crop_x + 1.0) / 2.0)))
                top = int(round(extra_height * ((crop_y + 1.0) / 2.0)))
                scaled = scaled.copy(left, top, size.width(), size.height())
            self._scaled_cache[scaled_key] = scaled
        return self._scaled_cache[scaled_key]


def image_target_rect(
    source_size: QSize,
    frame: QRectF,
    fit: str,
    transform: dict | None = None,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
) -> QRectF:
    """Map the original image into a frame using saved relative size and position."""
    values = normalize_image_transform(transform)
    fit = str(values.get("fit") or fit)
    source_width = max(1, source_size.width())
    source_height = max(1, source_size.height())
    if fit == "stretch":
        width, height = frame.width(), frame.height()
    else:
        ratios = (frame.width() / source_width, frame.height() / source_height)
        scale = max(ratios) if fit == "cover" else min(ratios)
        width, height = source_width * scale, source_height * scale
    center = frame.center()
    if fit == "cover":
        center.setX(center.x() - max(0.0, width - frame.width()) * crop_x / 2)
        center.setY(center.y() - max(0.0, height - frame.height()) * crop_y / 2)
    width *= float(values["scale_x"])
    height *= float(values["scale_y"])
    center.setX(center.x() + float(values["offset_x"]) * frame.width())
    center.setY(center.y() + float(values["offset_y"]) * frame.height())
    return QRectF(center.x() - width / 2, center.y() - height / 2, width, height)


def draw_image(
    painter: QPainter,
    cache: ImageCache,
    path: str,
    frame: QRect,
    fit: str,
    transform: dict | None = None,
    crop_x: float = 0.0,
    crop_y: float = 0.0,
) -> None:
    if frame.isEmpty():
        return
    painter.save()
    painter.setClipRect(frame, Qt.ClipOperation.IntersectClip)
    has_source = bool(path and Path(path).is_file())
    # Do not paint an opaque backing behind real images. Qt preserves the alpha
    # channel in PNG/WebP pixmaps, so transparent pixels should reveal the card
    # or canvas below them. Missing/corrupt images still use the opaque placeholder.
    if not has_source:
        painter.fillRect(frame, QColor("#111827"))
    if transform and has_source:
        pixmap = cache.pixmap(path)
        target = image_target_rect(pixmap.size(), QRectF(frame), fit, transform, crop_x, crop_y)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
    else:
        pixmap = cache.pixmap(path, frame.size(), fit=fit, crop_x=crop_x, crop_y=crop_y)
        target = QRect(
            frame.x() + (frame.width() - pixmap.width()) // 2,
            frame.y() + (frame.height() - pixmap.height()) // 2,
            pixmap.width(), pixmap.height(),
        )
        painter.drawPixmap(target, pixmap)
    painter.restore()


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
