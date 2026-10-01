from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.settings import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    MAX_PREVIEW_COLUMNS_1080P,
    MIN_PREVIEW_COLUMNS_1080P,
)
from app.utils.image_utils import ImageCache


class PreviewWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._project = Project.sample()
        self._current_time = 0.0
        self._selected_id = ""
        self._image_cache = ImageCache()

    def set_project(self, project: Project) -> None:
        self._project = project
        self.update()

    def set_current_time(self, seconds: float) -> None:
        self._current_time = max(0.0, seconds)
        self.update()

    def set_selected_item(self, item_id: str) -> None:
        self._selected_id = item_id
        self.update()

    def render_frame(self, seconds: float, size: QSize | None = None) -> QImage:
        previous_time = self._current_time
        previous_selection = self._selected_id
        self._current_time = max(0.0, seconds)
        self._selected_id = ""
        try:
            frame = self._render_canvas().toImage()
            if size is not None and size.isValid() and frame.size() != size:
                frame = frame.scaled(
                    size,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return frame
        finally:
            self._current_time = previous_time
            self._selected_id = previous_selection

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0d10"))
        preview_rect = self._preview_rect()
        canvas = self._render_canvas()
        painter.drawPixmap(preview_rect, canvas)
        painter.setPen(QPen(QColor("#47505c"), 1))
        painter.drawRect(preview_rect.adjusted(0, 0, -1, -1))
        painter.end()

    def _preview_rect(self) -> QRect:
        available = self.rect().adjusted(18, 18, -18, -18)
        if available.width() <= 0 or available.height() <= 0:
            return QRect()
        scale = min(available.width() / CANVAS_WIDTH, available.height() / CANVAS_HEIGHT)
        width = int(CANVAS_WIDTH * scale)
        height = int(CANVAS_HEIGHT * scale)
        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        return QRect(x, y, width, height)

    def _render_canvas(self) -> QPixmap:
        canvas = QPixmap(CANVAS_WIDTH, CANVAS_HEIGHT)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(canvas.rect(), QColor(self._project.canvas_background_color))

        visible_items = self._visible_items()
        if visible_items:
            self._draw_cards(painter, visible_items)
        else:
            self._draw_empty_state(painter)
        painter.end()
        return canvas

    def _visible_items(self) -> list[ComparisonItem]:
        return self._project.comparison_items

    def _draw_cards(self, painter: QPainter, items: list[ComparisonItem]) -> None:
        max_columns = max(
            MIN_PREVIEW_COLUMNS_1080P,
            min(MAX_PREVIEW_COLUMNS_1080P, self._project.preview_max_columns),
        )
        count = max_columns
        gap = 0
        side_margin = 0
        track_width = CANVAS_WIDTH - side_margin * 2
        card_width = max(1, int((track_width - gap * (count - 1)) / max(1, count)))
        y = 0
        card_height = CANVAS_HEIGHT - y
        x = side_margin
        slide_offset = self._slide_offset_units(len(items))
        step = card_width + gap
        viewport = QRect(0, y, CANVAS_WIDTH, card_height)

        painter.save()
        painter.setClipRect(viewport)
        for index, item in enumerate(items):
            card_x = int(x + (index - slide_offset) * step)
            rect = QRect(card_x, y, card_width, card_height)
            if rect.right() < viewport.left() or rect.left() > viewport.right():
                continue
            selected = item.id == self._selected_id
            active = item.start_time <= self._current_time <= item.start_time + item.duration
            self._draw_card(painter, rect, item, selected, active, max_columns)
        painter.restore()

    def _slide_offset_units(self, item_count: int) -> float:
        max_offset = max(0, item_count)
        if max_offset == 0:
            return 0.0
        segment_duration = max(0.1, self._project.item_fixed_duration)
        raw_offset = max(0.0, (self._current_time / segment_duration) - 1.0)
        return min(float(max_offset), raw_offset)

    def _draw_card(
        self,
        painter: QPainter,
        rect: QRect,
        item: ComparisonItem,
        selected: bool,
        active: bool,
        columns: int,
    ) -> None:
        painter.save()
        item_height = getattr(item, f"image_height_percent_{columns}", 0)
        project_height = getattr(self._project, f"image_height_percent_{columns}", 56)
        image_percent = max(35, min(75, item_height or project_height))
        fields = item.display_fields()
        image_fields = [field for field in fields if field.get("type") == "image"]
        content_fields = [field for field in fields if field.get("type") != "image"]
        image_height = int(rect.height() * image_percent / 100) if image_fields else 0
        if not content_fields:
            image_height = rect.height()
        remaining_height = rect.height() - image_height

        image_rect = QRect(rect.x(), rect.y(), rect.width(), image_height)
        image_fit = item.image_fit or self._project.image_fit
        if image_fields:
            image_y = image_rect.y()
            for index, image_field in enumerate(image_fields):
                images_left = len(image_fields) - index
                slice_height = (image_rect.bottom() - image_y + 1) // images_left
                image_slice = QRect(image_rect.x(), image_y, image_rect.width(), slice_height)
                painter.fillRect(image_slice, QColor("#111827"))
                pixmap = self._image_cache.pixmap(
                    str(image_field.get("value", "")), image_slice.size(), fit=image_fit
                )
                image_target = QRect(
                    image_slice.x() + (image_slice.width() - pixmap.width()) // 2,
                    image_slice.y() + (image_slice.height() - pixmap.height()) // 2,
                    pixmap.width(),
                    pixmap.height(),
                )
                painter.drawPixmap(image_target, pixmap)
                image_y += slice_height

        base_font_size = max(18, min(40, int(rect.width() * 0.072)))
        row_y = image_rect.bottom() + 1
        for index, field_data in enumerate(content_fields):
            rows_left = len(content_fields) - index
            row_height = (rect.bottom() - row_y + 1) // rows_left
            row_rect = QRect(rect.x(), row_y, rect.width(), row_height)
            role = self._field_role(field_data, index)
            font_size = base_font_size if role in {"name", "rank"} else max(
                17, int(base_font_size * 0.88)
            )
            self._draw_text_band(
                painter,
                row_rect,
                str(field_data.get("value", "")),
                self._field_style(item, field_data, role, "background_color"),
                self._field_style(item, field_data, role, "text_color"),
                font_size,
            )
            row_y += row_height

        border = QColor("#60a5fa" if selected else self._style(item, "card_border_color"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border, 5 if selected else 3))
        painter.drawRect(rect.adjusted(1, 1, -2, -2))
        painter.restore()

    def _style(self, item: ComparisonItem, name: str) -> str:
        return str(getattr(item, name, "") or getattr(self._project, name))

    def _field_style(
        self,
        item: ComparisonItem,
        field_data: dict[str, str],
        role: str,
        style_name: str,
    ) -> str:
        field_id = str(field_data.get("id", ""))
        field_style = self._project.field_styles.get(field_id, {})
        value = field_style.get(style_name, "")
        if value:
            return value
        return self._style(item, f"{role}_{style_name}")

    def _field_role(self, field_data: dict[str, str], index: int) -> str:
        role = str(field_data.get("role", ""))
        if role in {"name", "category", "rank", "value"}:
            return role
        field_type = field_data.get("type")
        if field_type == "name":
            return "name"
        if field_type == "number":
            return "rank"
        return "category" if index < 2 else "value"

    def _draw_text_band(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        background_color: str,
        text_color: str,
        font_size: int,
    ) -> None:
        painter.fillRect(rect, QColor(background_color))
        painter.setPen(QColor(text_color))
        target = rect.adjusted(14, 4, -14, -4)
        flags = Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap
        fitted_size = font_size
        while fitted_size > 12:
            font = QFont("Segoe UI", fitted_size, QFont.Weight.Bold)
            bounds = QFontMetrics(font).boundingRect(target, int(flags), text)
            if bounds.width() <= target.width() and bounds.height() <= target.height():
                break
            fitted_size -= 1
        painter.setFont(QFont("Segoe UI", fitted_size, QFont.Weight.Bold))
        painter.drawText(
            target,
            flags,
            text,
        )

    def _draw_empty_state(self, painter: QPainter) -> None:
        painter.setPen(QColor("#9ca3af"))
        painter.setFont(QFont("Segoe UI", 34, QFont.Weight.Bold))
        painter.drawText(QRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT), Qt.AlignmentFlag.AlignCenter, "Add comparison items to preview your video")
