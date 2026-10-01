from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.models.comparison_item import normalize_image_transform
from app.utils.image_utils import image_target_rect, placeholder_pixmap


class ImageEditorCanvas(QWidget):
    transform_changed = Signal(dict)
    HANDLE_DIRECTIONS = (
        (-1, -1), (0, -1), (1, -1), (1, 0),
        (1, 1), (0, 1), (-1, 1), (-1, 0),
    )

    def __init__(self, frame_size: QSize, fit: str, transform: dict, parent=None) -> None:
        super().__init__(parent)
        self.frame = QRectF(0, 0, frame_size.width(), frame_size.height())
        self.fit = fit
        self.transform = normalize_image_transform(transform)
        self.pixmap = placeholder_pixmap(QSize(320, 220))
        self.has_image = False
        self.keep_aspect = True
        self._drag: dict | None = None
        self.setMinimumSize(500, 360)
        self.setMouseTracking(True)
        self.setToolTip("Drag the image to move it. Drag the white handles to resize it.")

    def set_image(self, pixmap: QPixmap) -> None:
        self.has_image = not pixmap.isNull()
        self.pixmap = pixmap if self.has_image else placeholder_pixmap(QSize(320, 220))
        self.update()

    def set_transform(self, transform: dict) -> None:
        self.transform = normalize_image_transform(transform)
        self.update()

    def image_rect(self) -> QRectF:
        return image_target_rect(self.pixmap.size(), self.frame, self.fit, self.transform)

    def _mapping(self) -> tuple[float, QPointF]:
        if self._drag is not None:
            return self._drag["mapping"]
        bounds = self.frame.united(self.image_rect())
        available = QRectF(self.rect()).adjusted(36, 36, -36, -36)
        scale = min(available.width() / bounds.width(), available.height() / bounds.height())
        scale = max(0.001, scale)
        origin = available.center() - bounds.center() * scale
        return scale, origin

    def _screen_rect(self, rect: QRectF) -> QRectF:
        scale, origin = self._mapping()
        return QRectF(origin + rect.topLeft() * scale, rect.size() * scale)

    def _handles(self) -> list[QPointF]:
        rect = self._screen_rect(self.image_rect())
        return [
            QPointF(rect.center().x() + dx * rect.width() / 2,
                    rect.center().y() + dy * rect.height() / 2)
            for dx, dy in self.HANDLE_DIRECTIONS
        ]

    def _handle_at(self, point: QPointF) -> int | None:
        for index, handle in enumerate(self._handles()):
            if QRectF(handle.x() - 9, handle.y() - 9, 18, 18).contains(point):
                return index
        return None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#0b0d10"))
        frame = self._screen_rect(self.frame)
        image = self._screen_rect(self.image_rect())
        painter.fillRect(frame, QColor("#111827"))
        painter.setOpacity(0.25)
        painter.drawPixmap(image, self.pixmap, QRectF(self.pixmap.rect()))
        painter.setOpacity(1)
        painter.save()
        painter.setClipRect(frame)
        painter.drawPixmap(image, self.pixmap, QRectF(self.pixmap.rect()))
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DashLine))
        painter.drawRect(frame)
        if self.has_image:
            painter.setPen(QPen(QColor("#8b5cf6"), 2))
            painter.drawRect(image)
            painter.setPen(QPen(QColor("#aeb6c2"), 1))
            painter.setBrush(QColor("#ffffff"))
            for handle in self._handles():
                painter.drawEllipse(handle, 5, 5)
        else:
            painter.setPen(QColor("#ffffff"))
            painter.drawText(self.rect().adjusted(0, 8, 0, 0),
                             Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter,
                             "Choose an image to start editing")
        painter.end()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self.has_image:
            return super().mousePressEvent(event)
        point = event.position()
        handle = self._handle_at(point)
        if handle is None and not self._screen_rect(self.image_rect()).contains(point):
            return super().mousePressEvent(event)
        mapping = self._mapping()
        self._drag = {
            "mapping": mapping,
            "start": point,
            "rect": self.image_rect(),
            "transform": dict(self.transform),
            "handle": handle,
        }
        self.setCursor(Qt.CursorShape.ClosedHandCursor if handle is None else self._handle_cursor(handle))
        event.accept()

    def _handle_cursor(self, index: int) -> Qt.CursorShape:
        dx, dy = self.HANDLE_DIRECTIONS[index]
        if dx == 0:
            return Qt.CursorShape.SizeVerCursor
        if dy == 0:
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.SizeFDiagCursor if dx == dy else Qt.CursorShape.SizeBDiagCursor

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag is None:
            handle = self._handle_at(event.position()) if self.has_image else None
            if handle is not None:
                self.setCursor(self._handle_cursor(handle))
            elif self.has_image and self._screen_rect(self.image_rect()).contains(event.position()):
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            return super().mouseMoveEvent(event)
        scale, _origin = self._drag["mapping"]
        delta = (event.position() - self._drag["start"]) / scale
        original = self._drag["rect"]
        values = dict(self._drag["transform"])
        handle = self._drag["handle"]
        if handle is None:
            values["offset_x"] = float(values["offset_x"]) + delta.x() / self.frame.width()
            values["offset_y"] = float(values["offset_y"]) + delta.y() / self.frame.height()
        else:
            dx, dy = self.HANDLE_DIRECTIONS[handle]
            factor_x = 1 + dx * delta.x() / original.width() if dx else 1.0
            factor_y = 1 + dy * delta.y() / original.height() if dy else 1.0
            if self.keep_aspect:
                factor = factor_x if dx else factor_y
                if dx and dy and abs(factor_y - 1) > abs(factor_x - 1):
                    factor = factor_y
                minimum = max(0.1 / float(values["scale_x"]), 0.1 / float(values["scale_y"]))
                maximum = min(5 / float(values["scale_x"]), 5 / float(values["scale_y"]))
                factor_x = factor_y = max(minimum, min(maximum, factor))
            values["scale_x"] = float(values["scale_x"]) * factor_x
            values["scale_y"] = float(values["scale_y"]) * factor_y
            values = normalize_image_transform(values)
            base = image_target_rect(self.pixmap.size(), self.frame, self.fit,
                                     {"fit": values.get("fit", self.fit)})
            width = base.width() * float(values["scale_x"])
            height = base.height() * float(values["scale_y"])
            center = original.center() + QPointF(dx * (width - original.width()) / 2,
                                                 dy * (height - original.height()) / 2)
            values["offset_x"] = (center.x() - self.frame.center().x()) / self.frame.width()
            values["offset_y"] = (center.y() - self.frame.center().y()) / self.frame.height()
        self.set_transform(values)
        self.transform_changed.emit(dict(self.transform))
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)
