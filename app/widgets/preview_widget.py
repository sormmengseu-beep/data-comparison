from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.settings import (
    MAX_PREVIEW_COLUMNS_1080P,
    MIN_PREVIEW_COLUMNS_1080P,
)
from app.utils.image_utils import ImageCache, draw_image, image_target_rect
from app.utils.shape_utils import fill_brush, shape_path


class PreviewWidget(QWidget):
    image_edit_requested = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(480, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._project = Project.sample()
        self._current_time = 0.0
        self._selected_id = ""
        self._image_cache = ImageCache()
        self._background_path = ""
        self._background_pixmap = QPixmap()
        self._image_regions: list[tuple[QRect, str, str]] = []
        self.setMouseTracking(True)
        self.setToolTip("Click an image to resize or reposition it")

    def set_project(self, project: Project) -> None:
        self._project = project
        self._background_path = ""
        self._background_pixmap = QPixmap()
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
        previous_regions = self._image_regions
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
            self._image_regions = previous_regions

    def _image_at(self, point: QPoint) -> tuple[str, str] | None:
        preview = self._preview_rect()
        if preview.isEmpty() or not preview.contains(point):
            return None
        canvas_point = QPoint(
            int((point.x() - preview.x()) * self._project.width / preview.width()),
            int((point.y() - preview.y()) * self._project.height / preview.height()),
        )
        for region, item_id, field_id in reversed(self._image_regions):
            if region.contains(canvas_point):
                return item_id, field_id
        return None

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._render_canvas()
            target = self._image_at(event.position().toPoint())
            if target is not None:
                self.image_edit_requested.emit(*target)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._image_at(event.position().toPoint()) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        background = self.palette().base().color()
        background.setAlpha(100)
        painter.fillRect(self.rect(), background)
        preview_rect = self._preview_rect()
        canvas = self._render_canvas()
        painter.drawPixmap(preview_rect, canvas)
        border = self.palette().text().color()
        border.setAlpha(45)
        painter.setPen(QPen(border, 1))
        painter.drawRect(preview_rect.adjusted(0, 0, -1, -1))
        painter.end()

    def _preview_rect(self) -> QRect:
        available = self.rect().adjusted(18, 18, -18, -18)
        if available.width() <= 0 or available.height() <= 0:
            return QRect()
        canvas_width = max(1, self._project.width)
        canvas_height = max(1, self._project.height)
        scale = min(
            available.width() / canvas_width,
            available.height() / canvas_height,
        )
        width = int(canvas_width * scale)
        height = int(canvas_height * scale)
        x = available.x() + (available.width() - width) // 2
        y = available.y() + (available.height() - height) // 2
        return QRect(x, y, width, height)

    def _render_canvas(self) -> QPixmap:
        self._image_regions = []
        canvas_width = max(1, self._project.width)
        canvas_height = max(1, self._project.height)
        canvas = QPixmap(canvas_width, canvas_height)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(canvas.rect(), QColor(self._project.canvas_background_color))
        background_path = self._project.canvas_background_image
        if background_path != self._background_path:
            self._background_path = background_path
            self._background_pixmap = QPixmap(background_path) if background_path else QPixmap()
        if not self._background_pixmap.isNull():
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            target = image_target_rect(
                self._background_pixmap.size(), QRectF(canvas.rect()),
                self._project.canvas_background_fit,
            )
            painter.drawPixmap(target, self._background_pixmap, QRectF(self._background_pixmap.rect()))
            painter.restore()

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
        canvas_width = max(1, self._project.width)
        canvas_height = max(1, self._project.height)
        track_width = canvas_width - side_margin * 2
        card_width = max(1, int((track_width - gap * (count - 1)) / max(1, count)))
        y = 0
        card_height = canvas_height - y
        x = side_margin
        slide_offset = self._slide_offset_units(len(items))
        step = card_width + gap
        viewport = QRect(0, y, canvas_width, card_height)

        painter.save()
        painter.setClipRect(viewport)
        for index, item in enumerate(items):
            card_x = int(x + (index - slide_offset) * step)
            rect = QRect(card_x, y, card_width, card_height)
            if not viewport.intersects(rect):
                continue
            selected = item.id == self._selected_id
            active = item.start_time <= self._current_time <= item.start_time + item.duration
            self._draw_opening_card(painter, rect, item, selected, active, max_columns, index)
        painter.restore()

    def _draw_opening_card(
        self,
        painter: QPainter,
        rect: QRect,
        item: ComparisonItem,
        selected: bool,
        active: bool,
        columns: int,
        index: int,
    ) -> None:
        animation = self._project.opening_animation
        # Use the existing opening segment, then continue the horizontal scroll.
        duration = max(0.1, self._project.item_fixed_duration)
        if index >= columns or animation == "slide_left" or self._current_time >= duration:
            self._draw_card(painter, rect, item, selected, active, columns)
            return
        progress = min(1.0, max(0.0, self._current_time / duration))
        if animation in {"stagger_bottom", "stagger_top", "alternating"}:
            count = min(columns, len(self._project.comparison_items))
            delay = 0.3 * index / max(1, count - 1)
            progress = min(1.0, max(0.0, (progress - delay) / 0.7))
        if progress <= 0.0:
            return
        eased = 1.0 - (1.0 - progress) ** 3
        opacity = 1.0
        scale = 1.0
        if animation in {"from_bottom", "from_top", "stagger_bottom", "stagger_top", "alternating"}:
            direction = -1 if animation in {"from_top", "stagger_top"} else 1
            if animation == "alternating":
                direction = 1 if index % 2 == 0 else -1
            rect = rect.translated(0, direction * round(rect.height() * (1.0 - eased)))
        elif animation == "bounce_bottom":
            # Ease-out bounce: each landing becomes smaller before settling.
            bounce = self._ease_out_bounce(progress)
            rect = rect.translated(0, round(rect.height() * (1.0 - bounce)))
        elif animation == "fade_in":
            opacity = eased
        elif animation == "zoom_in":
            scale = 0.55 + 0.45 * eased
            opacity = eased
        elif animation == "pop_in":
            back = 1.0 + 2.70158 * (progress - 1.0) ** 3 + 1.70158 * (progress - 1.0) ** 2
            scale = 0.65 + 0.35 * back
            opacity = eased

        painter.save()
        painter.setOpacity(opacity)
        if animation == "reveal_left":
            reveal = QRect(
                0,
                0,
                round(max(1, self._project.width) * eased),
                max(1, self._project.height),
            )
            painter.setClipRect(reveal, Qt.ClipOperation.IntersectClip)
        # Keep all content, including fonts and image crops, at the same scale.
        if scale != 1.0:
            # A pop may briefly overshoot; keep each box inside its own slot.
            painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
            center = rect.center()
            painter.translate(center)
            painter.scale(scale, scale)
            painter.translate(-center)
        self._draw_card(painter, rect, item, selected, active, columns)
        painter.restore()

    @staticmethod
    def _ease_out_bounce(progress: float) -> float:
        if progress < 1.0 / 2.75:
            return 7.5625 * progress * progress
        if progress < 2.0 / 2.75:
            progress -= 1.5 / 2.75
            return 7.5625 * progress * progress + 0.75
        if progress < 2.5 / 2.75:
            progress -= 2.25 / 2.75
            return 7.5625 * progress * progress + 0.9375
        progress -= 2.625 / 2.75
        return 7.5625 * progress * progress + 0.984375

    def _slide_offset_units(self, item_count: int) -> float:
        columns = max(
            MIN_PREVIEW_COLUMNS_1080P,
            min(MAX_PREVIEW_COLUMNS_1080P, self._project.preview_max_columns),
        )
        # Stop once the final page fills the layout instead of scrolling until
        # only the last card remains on screen.
        max_offset = max(0, item_count - columns)
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
        fields_by_id = {str(field.get("id", "")): field for field in fields}
        children_by_parent: dict[str, list[dict[str, str]]] = {}
        root_fields: list[dict[str, str]] = []
        for field in fields:
            field_id = str(field.get("id", ""))
            parent_id = str(
                self._project.field_styles.get(field_id, {}).get("parent_id", "")
            )
            parent = fields_by_id.get(parent_id)
            if (
                field.get("type") != "image"
                and parent is not None
                and parent.get("type") == "image"
            ):
                children_by_parent.setdefault(parent_id, []).append(field)
            else:
                root_fields.append(field)
        image_fields = [field for field in root_fields if field.get("type") == "image"]
        content_fields = [field for field in root_fields if field.get("type") != "image"]
        image_height = int(rect.height() * image_percent / 100) if image_fields else 0
        if not content_fields:
            image_height = rect.height()
        text_height = rect.height() - image_height
        image_fit = item.image_fit or self._project.image_fit
        base_font_size = self._project.text_font_size or max(
            18, min(40, int(rect.width() * 0.072))
        )
        row_styles = [
            self._resolved_field_style(item, field_data, self._field_role(field_data, index))
            for index, field_data in enumerate(content_fields)
        ]
        text_weights = [
            self._style_int(style, "height_weight", 100, 25, 400)
            for style in row_styles
        ]
        image_weights = [
            self._style_int(
                self._project.field_styles.get(str(field.get("id", "")), {}),
                "height_weight",
                100,
                25,
                400,
            )
            for field in image_fields
        ]
        remaining_image_pixels = image_height
        remaining_image_weight = sum(image_weights)
        remaining_text_pixels = text_height
        remaining_text_weight = sum(text_weights)
        row_y = rect.y()
        image_index = 0
        content_index = 0
        for field_data in root_fields:
            field_type = str(field_data.get("type", "text"))
            field_id = str(field_data.get("id", ""))
            if field_type == "image":
                image_weight = image_weights[image_index]
                row_height = (
                    remaining_image_pixels
                    if image_index == len(image_fields) - 1
                    else max(
                        1,
                        round(
                            remaining_image_pixels
                            * image_weight
                            / max(1, remaining_image_weight)
                        ),
                    )
                )
            else:
                weight = text_weights[content_index]
                row_height = (
                    remaining_text_pixels
                    if content_index == len(content_fields) - 1
                    else max(
                        1,
                        round(
                            remaining_text_pixels
                            * weight
                            / max(1, remaining_text_weight)
                        ),
                    )
                )
            fallback_rect = QRect(rect.x(), row_y, rect.width(), row_height)
            field_style = self._project.field_styles.get(field_id, {})
            row_rect = self._overlay_rect(rect, fallback_rect, field_style)
            if field_type == "image":
                painter.save()
                painter.setClipPath(
                    shape_path(
                        row_rect,
                        field_style.get("shape", "rectangle"),
                        self._style_int(field_style, "corner_radius", 0, 0, 64),
                    ),
                    Qt.ClipOperation.IntersectClip,
                )
                draw_image(
                    painter,
                    self._image_cache,
                    str(field_data.get("value", "")),
                    row_rect,
                    image_fit,
                    item.image_transforms.get(field_id),
                    item.image_crop_x,
                    item.image_crop_y,
                )
                visible_slice = row_rect.intersected(
                    painter.clipBoundingRect().toAlignedRect()
                )
                image_region = painter.transform().mapRect(visible_slice).intersected(
                    QRect(0, 0, max(1, self._project.width), max(1, self._project.height))
                )
                if not image_region.isEmpty():
                    self._image_regions.append((image_region, item.id, field_id))
                child_fields = children_by_parent.get(field_id, [])
                self._draw_image_gradient(painter, row_rect, field_style)
                painter.restore()
                if child_fields:
                    child_styles = [
                        self._resolved_field_style(
                            item,
                            child,
                            self._field_role(child, child_index),
                        )
                        for child_index, child in enumerate(child_fields)
                    ]
                    child_weights = [
                        self._style_int(style, "height_weight", 100, 25, 400)
                        for style in child_styles
                    ]
                    child_y = row_rect.y()
                    child_pixels = row_rect.height()
                    child_weight_total = sum(child_weights)
                    for child_index, child in enumerate(child_fields):
                        child_weight = child_weights[child_index]
                        child_height = (
                            child_pixels
                            if child_index == len(child_fields) - 1
                            else max(
                                1,
                                round(
                                    child_pixels
                                    * child_weight
                                    / max(1, child_weight_total)
                                ),
                            )
                        )
                        child_rect = QRect(
                            row_rect.x(), child_y, row_rect.width(), child_height
                        )
                        child_rect = self._overlay_rect(
                            row_rect, child_rect, child_styles[child_index]
                        )
                        child_role = self._field_role(child, child_index)
                        default_size = (
                            base_font_size
                            if child_role in {"name", "rank"}
                            else max(
                                1 if self._project.text_font_size else 17,
                                int(base_font_size * 0.88),
                            )
                        )
                        child_size = self._style_int(
                            child_styles[child_index], "font_size", 0, 0, 120
                        ) or default_size
                        self._draw_text_band(
                            painter,
                            child_rect,
                            str(child.get("value", "")),
                            child_styles[child_index],
                            child_size,
                            overlay=True,
                        )
                        child_y += child_height
                        child_pixels -= child_height
                        child_weight_total -= child_weight
                row_y += row_height
                remaining_image_pixels -= row_height
                remaining_image_weight -= image_weight
                image_index += 1
                continue

            role = self._field_role(field_data, content_index)
            style = row_styles[content_index]
            default_font_size = base_font_size if role in {"name", "rank"} else max(
                1 if self._project.text_font_size else 17,
                int(base_font_size * 0.88),
            )
            font_size = self._style_int(style, "font_size", 0, 0, 120) or default_font_size
            self._draw_text_band(
                painter,
                row_rect,
                str(field_data.get("value", "")),
                style,
                font_size,
            )
            row_y += row_height
            remaining_text_pixels -= row_height
            remaining_text_weight -= weight
            content_index += 1

        painter.setBrush(Qt.BrushStyle.NoBrush)
        border = QColor(self._style(item, "card_border_color"))
        border_width = self._project.card_border_width
        if border_width > 0:
            painter.setPen(QPen(border, border_width))
            inset = max(1, (border_width + 1) // 2)
            painter.drawRect(rect.adjusted(inset, inset, -inset, -inset))
        if selected:
            # Selection is an editor-only affordance. Draw it separately from the
            # configured border so selecting a card does not hide its chosen color.
            selection_pen = QPen(QColor("#60a5fa"), 2)
            selection_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(selection_pen)
            selection_inset = max(2, border_width + 2)
            painter.drawRect(
                rect.adjusted(
                    selection_inset,
                    selection_inset,
                    -selection_inset,
                    -selection_inset,
                )
            )
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

    def _resolved_field_style(
        self,
        item: ComparisonItem,
        field_data: dict[str, str],
        role: str,
    ) -> dict[str, str]:
        field_id = str(field_data.get("id", ""))
        saved = self._project.field_styles.get(field_id, {})
        return {
            "background_color": saved.get("background_color")
            or self._style(item, f"{role}_background_color"),
            "text_color": saved.get("text_color")
            or self._style(item, f"{role}_text_color"),
            "outline_color": saved.get("outline_color", "#000000"),
            "outline_width": saved.get("outline_width", "0"),
            "border_color": saved.get("border_color", "#000000"),
            "border_width": saved.get("border_width", "0"),
            "container_color": saved.get("container_color", ""),
            "inset": saved.get("inset", "0"),
            "corner_radius": saved.get("corner_radius", "0"),
            "alignment": saved.get("alignment", "center"),
            "font_size": saved.get("font_size", "0"),
            "height_weight": saved.get("height_weight", "100"),
            "padding": saved.get("padding", "14"),
            "font_weight": saved.get("font_weight", "700"),
            "parent_id": saved.get("parent_id", ""),
            "shape": (
                saved.get("shape", "rectangle")
                if field_data.get("type") == "shape"
                else "rectangle"
            ),
            "fill_mode": saved.get("fill_mode", "solid"),
            "gradient_color_2": saved.get("gradient_color_2")
            or saved.get("background_color")
            or self._style(item, f"{role}_background_color"),
            "overlay_x": saved.get("overlay_x", ""),
            "overlay_y": saved.get("overlay_y", ""),
            "overlay_width": saved.get("overlay_width", ""),
            "overlay_height": saved.get("overlay_height", ""),
        }

    def _draw_image_gradient(
        self, painter: QPainter, rect: QRect, style: dict[str, str]
    ) -> None:
        mode = str(style.get("gradient_mode") or "none")
        if mode == "none":
            return
        opacity = self._style_int(style, "gradient_opacity", 65, 0, 100)
        color = QColor(style.get("gradient_color") or "#000000")
        color.setAlpha(round(255 * opacity / 100))
        if mode == "tint":
            painter.fillRect(rect, color)
            return
        transparent = QColor(color)
        transparent.setAlpha(0)
        if mode == "top":
            gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        elif mode == "left":
            gradient = QLinearGradient(rect.topLeft(), rect.topRight())
        elif mode == "right":
            gradient = QLinearGradient(rect.topRight(), rect.topLeft())
        else:
            gradient = QLinearGradient(rect.bottomLeft(), rect.topLeft())
        gradient.setColorAt(0.0, color)
        gradient.setColorAt(0.72, transparent)
        painter.fillRect(rect, gradient)

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
        style: dict[str, str],
        font_size: int,
        overlay: bool = False,
    ) -> None:
        background_color = QColor(style["background_color"])
        inset = self._style_int(style, "inset", 0, 0, 96)
        band_rect = rect.adjusted(inset, 0, -inset, 0)
        corner_radius = self._style_int(style, "corner_radius", 0, 0, 64)
        painter.setPen(Qt.PenStyle.NoPen)
        if (
            not overlay
            or inset
            or corner_radius
            or style.get("shape", "rectangle") != "rectangle"
            or style.get("fill_mode", "solid") != "solid"
        ):
            painter.setBrush(
                fill_brush(
                    band_rect,
                    background_color.name(),
                    style.get("gradient_color_2", background_color.name()),
                    style.get("fill_mode", "solid"),
                )
            )
            painter.drawPath(
                shape_path(
                    band_rect,
                    style.get("shape", "rectangle"),
                    corner_radius,
                )
            )
        padding = self._style_int(style, "padding", 14, 0, 64)
        target = band_rect.adjusted(padding, 4, -padding, -4)
        horizontal = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(style.get("alignment", "center"), Qt.AlignmentFlag.AlignHCenter)
        flags = horizontal | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
        weight_value = self._style_int(style, "font_weight", 700, 100, 900)
        weight_value = min(
            (100, 200, 300, 400, 500, 600, 700, 800, 900),
            key=lambda value: abs(value - weight_value),
        )
        weight = QFont.Weight(weight_value)
        fitted_size = font_size
        while fitted_size > 12:
            font = QFont(self._project.text_font_family, fitted_size, weight)
            bounds = QFontMetrics(font).boundingRect(target, int(flags), text)
            if bounds.width() <= target.width() and bounds.height() <= target.height():
                break
            fitted_size -= 1
        painter.setFont(QFont(self._project.text_font_family, fitted_size, weight))
        outline_width = self._style_int(style, "outline_width", 0, 0, 8)
        if outline_width:
            painter.setPen(QColor(style.get("outline_color", "#000000")))
            for distance in range(1, outline_width + 1):
                for dx, dy in (
                    (-distance, -distance), (0, -distance), (distance, -distance),
                    (-distance, 0), (distance, 0),
                    (-distance, distance), (0, distance), (distance, distance),
                ):
                    painter.drawText(target.translated(dx, dy), flags, text)
        painter.setPen(QColor(style["text_color"]))
        painter.drawText(
            target,
            flags,
            text,
        )
        border_width = self._style_int(style, "border_width", 0, 0, 12)
        if border_width:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(style.get("border_color", "#000000")), border_width))
            inset = max(1, border_width // 2)
            border_rect = band_rect.adjusted(inset, inset, -inset, -inset)
            painter.drawPath(
                shape_path(
                    border_rect,
                    style.get("shape", "rectangle"),
                    corner_radius,
                )
            )

    @staticmethod
    def _overlay_rect(parent: QRect, fallback: QRect, style: dict[str, str]) -> QRect:
        keys = ("overlay_x", "overlay_y", "overlay_width", "overlay_height")
        if any(style.get(key, "") in (None, "") for key in keys):
            return fallback
        try:
            x_value = max(0, min(1000, int(style["overlay_x"])))
            y_value = max(0, min(1000, int(style["overlay_y"])))
            width_value = max(20, min(1000, int(style["overlay_width"])))
            height_value = max(20, min(1000, int(style["overlay_height"])))
        except (TypeError, ValueError):
            return fallback
        width_value = min(width_value, 1000 - x_value)
        height_value = min(height_value, 1000 - y_value)
        return QRect(
            parent.x() + round(parent.width() * x_value / 1000),
            parent.y() + round(parent.height() * y_value / 1000),
            max(1, round(parent.width() * width_value / 1000)),
            max(1, round(parent.height() * height_value / 1000)),
        )

    @staticmethod
    def _style_int(
        style: dict[str, str], key: str, default: int, minimum: int, maximum: int
    ) -> int:
        try:
            value = int(style.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _draw_empty_state(self, painter: QPainter) -> None:
        painter.setPen(QColor("#9ca3af"))
        painter.setFont(QFont(self._project.text_font_family, 34, QFont.Weight.Bold))
        painter.drawText(
            QRect(0, 0, max(1, self._project.width), max(1, self._project.height)),
            Qt.AlignmentFlag.AlignCenter,
            "Add comparison items to preview your video",
        )
