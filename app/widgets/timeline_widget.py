from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.settings import MIN_CLIP_DURATION
from app.utils.time_utils import clamp, format_ruler_time, format_timestamp
from app.widgets.timeline_clip import PaintedClip
from app.widgets.timeline_track import DEFAULT_TRACKS


TIMELINE_COLORS = {
    "dark": {
        "canvas": "#12161c",
        "ruler": "#171c23",
        "ruler_line": "#6b7280",
        "major_tick": "#9ca3af",
        "minor_tick": "#4b5563",
        "text": "#d1d5db",
        "row_even": "#161b22",
        "row_odd": "#14181f",
        "divider": "#27303a",
    },
    "light": {
        "canvas": "#eef2f7",
        "ruler": "#ffffff",
        "ruler_line": "#b8c3d1",
        "major_tick": "#667085",
        "minor_tick": "#b8c3d1",
        "text": "#344054",
        "row_even": "#ffffff",
        "row_odd": "#f8fafc",
        "divider": "#d9e0e8",
    },
}


class TimelineCanvas(QWidget):
    item_selected = Signal(str)
    item_timing_changed = Signal(str, float, float)
    time_changed = Signal(float)
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.project = Project.sample()
        self.pixels_per_second = 80
        self.current_time = 0.0
        self.selected_id = ""
        self.theme = "dark"
        self.left_margin = 132
        self.ruler_height = 42
        self.track_height = 48
        self.track_gap = 8
        self._clips: list[PaintedClip] = []
        self._drag_mode = ""
        self._drag_item_id = ""
        self._drag_start_pos = QPoint()
        self._original_start = 0.0
        self._original_duration = 0.0
        self._set_content_size()

    def set_project(self, project: Project) -> None:
        self.project = project
        self.current_time = clamp(self.current_time, 0.0, self.project.total_duration())
        self._set_content_size()
        self.update()

    def set_pixels_per_second(self, value: int) -> None:
        self.pixels_per_second = int(clamp(value, 1, 500))
        self._set_content_size()
        self.update()

    def set_current_time(self, seconds: float) -> None:
        self.current_time = clamp(seconds, 0.0, self.project.total_duration())
        self.update()

    def set_selected_item(self, item_id: str) -> None:
        self.selected_id = item_id
        self.update()

    def set_theme(self, theme: str) -> None:
        self.theme = theme if theme in TIMELINE_COLORS else "dark"
        self.update()

    def _color(self, name: str) -> QColor:
        return QColor(TIMELINE_COLORS[self.theme][name])

    def _set_content_size(self) -> None:
        width = int(self.left_margin + self.project.total_duration() * self.pixels_per_second + 36)
        height = self.ruler_height + len(DEFAULT_TRACKS) * (self.track_height + self.track_gap) + 28
        self.setMinimumSize(max(900, width), height)
        self.resize(max(900, width), height)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self._color("canvas"))
        self._clips = []
        self._draw_ruler(painter)
        self._draw_tracks(painter)
        self._draw_playhead(painter)
        painter.end()

    def _draw_ruler(self, painter: QPainter) -> None:
        painter.fillRect(QRect(0, 0, self.width(), self.ruler_height), self._color("ruler"))
        painter.setPen(self._color("ruler_line"))
        painter.drawLine(self.left_margin, self.ruler_height - 1, self.width(), self.ruler_height - 1)
        tick_seconds = self._tick_seconds()
        minor = tick_seconds / 5
        total = self.project.total_duration()
        painter.setFont(QFont("Segoe UI", 9))
        t = 0.0
        while t <= total:
            x = self.time_to_x(t)
            is_major = abs((t / tick_seconds) - round(t / tick_seconds)) < 0.001
            height = 18 if is_major else 8
            painter.setPen(self._color("major_tick" if is_major else "minor_tick"))
            painter.drawLine(x, self.ruler_height - height, x, self.ruler_height - 1)
            if is_major:
                painter.drawText(QRect(x + 4, 5, 90, 18), Qt.AlignmentFlag.AlignLeft, format_ruler_time(t))
            t += minor
        painter.setPen(self._color("text"))
        painter.drawText(QRect(10, 11, 110, 18), Qt.AlignmentFlag.AlignLeft, format_timestamp(self.current_time))

    def _draw_tracks(self, painter: QPainter) -> None:
        y = self.ruler_height + 8
        for track in DEFAULT_TRACKS:
            row = QRect(0, y, self.width(), self.track_height)
            painter.fillRect(
                row,
                self._color("row_even" if DEFAULT_TRACKS.index(track) % 2 == 0 else "row_odd"),
            )
            painter.setPen(self._color("text"))
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            painter.drawText(QRect(14, y, self.left_margin - 24, self.track_height), Qt.AlignmentFlag.AlignVCenter, track.name)
            painter.setPen(self._color("divider"))
            painter.drawLine(self.left_margin, y, self.width(), y)
            if track.name == "Comparison":
                self._draw_comparison_clips(painter, y, track.color)
            elif track.name == "Images":
                self._draw_image_markers(painter, y, track.color)
            y += self.track_height + self.track_gap

    def _draw_comparison_clips(self, painter: QPainter, y: int, color: QColor) -> None:
        for item in self.project.comparison_items:
            x = self.time_to_x(item.start_time)
            width = max(8, int(item.duration * self.pixels_per_second))
            rect = QRect(x, y + 7, width, self.track_height - 14)
            self._clips.append(PaintedClip(item.id, "Comparison", rect))
            selected = item.id == self.selected_id
            fill = QColor("#2563eb" if selected else color.name())
            painter.setBrush(fill)
            painter.setPen(QPen(QColor("#bfdbfe" if selected else "#1d4ed8"), 2 if selected else 1))
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.drawText(rect.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, item.name)

    def _draw_image_markers(self, painter: QPainter, y: int, color: QColor) -> None:
        painter.setBrush(QColor(color.name()))
        painter.setPen(QPen(QColor("#065f46"), 1))
        for item in self.project.comparison_items:
            if not item.image_path:
                continue
            rect = QRect(self.time_to_x(item.start_time), y + 12, max(8, int(item.duration * self.pixels_per_second)), self.track_height - 24)
            painter.drawRoundedRect(rect, 4, 4)

    def _draw_playhead(self, painter: QPainter) -> None:
        x = self.time_to_x(self.current_time)
        painter.setPen(QPen(QColor("#f43f5e"), 2))
        painter.drawLine(x, 0, x, self.height())
        painter.setBrush(QColor("#f43f5e"))
        painter.setPen(Qt.PenStyle.NoPen)
        points = [
            QPoint(x - 8, 0),
            QPoint(x + 8, 0),
            QPoint(x + 8, 16),
            QPoint(x, 25),
            QPoint(x - 8, 16),
        ]
        painter.drawPolygon(points)

    def _tick_seconds(self) -> float:
        for value in (0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600):
            if value * self.pixels_per_second >= 75:
                return value
        return 600

    def time_to_x(self, seconds: float) -> int:
        return int(self.left_margin + seconds * self.pixels_per_second)

    def x_to_time(self, x: int) -> float:
        return clamp((x - self.left_margin) / self.pixels_per_second, 0.0, self.project.total_duration())

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus()
        if event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        if position.y() <= self.ruler_height:
            self._drag_mode = "playhead"
            self._set_time_from_x(position.x())
            return
        clip = self._clip_at(position)
        if clip is None:
            self._drag_mode = ""
            return
        self.selected_id = clip.item_id
        self.item_selected.emit(clip.item_id)
        item = self.project.item_by_id(clip.item_id)
        if item is None:
            return
        edge = 7
        if abs(position.x() - clip.rect.left()) <= edge:
            self._drag_mode = "resize_left"
        elif abs(position.x() - clip.rect.right()) <= edge:
            self._drag_mode = "resize_right"
        else:
            self._drag_mode = "move"
        self._drag_item_id = clip.item_id
        self._drag_start_pos = position
        self._original_start = item.start_time
        self._original_duration = item.duration
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        position = event.position().toPoint()
        if self._drag_mode == "playhead":
            self._set_time_from_x(position.x())
            return
        if not self._drag_mode or not self._drag_item_id:
            self._update_cursor(position)
            return
        item = self.project.item_by_id(self._drag_item_id)
        if item is None:
            return
        delta_seconds = (position.x() - self._drag_start_pos.x()) / self.pixels_per_second
        start = self._original_start
        duration = self._original_duration
        if self._drag_mode == "move":
            start = max(0.0, self._original_start + delta_seconds)
        elif self._drag_mode == "resize_left":
            proposed_start = max(0.0, self._original_start + delta_seconds)
            end = self._original_start + self._original_duration
            start = min(proposed_start, end - MIN_CLIP_DURATION)
            duration = end - start
        elif self._drag_mode == "resize_right":
            duration = max(MIN_CLIP_DURATION, self._original_duration + delta_seconds)
        item.start_time = start
        item.duration = duration
        self.item_timing_changed.emit(item.id, start, duration)
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_mode = ""
        self._drag_item_id = ""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_requested.emit()
        else:
            super().keyPressEvent(event)

    def _clip_at(self, position: QPoint) -> PaintedClip | None:
        for clip in reversed(self._clips):
            if clip.rect.contains(position):
                return clip
        return None

    def _update_cursor(self, position: QPoint) -> None:
        clip = self._clip_at(position)
        if clip is None:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if abs(position.x() - clip.rect.left()) <= 7 or abs(position.x() - clip.rect.right()) <= 7:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def _set_time_from_x(self, x: int) -> None:
        self.current_time = self.x_to_time(x)
        self.time_changed.emit(self.current_time)
        self.update()


class TimelineWidget(QWidget):
    item_selected = Signal(str)
    item_timing_changed = Signal(str, float, float)
    time_changed = Signal(float)
    delete_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        controls = QHBoxLayout()
        title = QLabel("TIMELINE")
        title.setObjectName("PanelTitle")
        self.time_label = QLabel("00:00.000")
        zoom_minus = QLabel("-")
        zoom_plus = QLabel("+")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(1, 500)
        self.zoom_slider.setValue(80)
        self.zoom_slider.setFixedWidth(260)
        controls.addWidget(title)
        controls.addSpacing(20)
        controls.addWidget(QLabel("Current Time"))
        controls.addWidget(self.time_label)
        controls.addStretch(1)
        controls.addWidget(zoom_minus)
        controls.addWidget(self.zoom_slider)
        controls.addWidget(zoom_plus)
        layout.addLayout(controls)

        self.canvas = TimelineCanvas()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setWidget(self.canvas)
        layout.addWidget(self.scroll, 1)

        self.zoom_slider.valueChanged.connect(self.canvas.set_pixels_per_second)
        self.canvas.item_selected.connect(self.item_selected.emit)
        self.canvas.item_timing_changed.connect(self.item_timing_changed.emit)
        self.canvas.time_changed.connect(self._time_changed)
        self.canvas.delete_requested.connect(self.delete_requested.emit)

    def set_project(self, project: Project) -> None:
        self.canvas.set_project(project)
        QTimer.singleShot(0, self.fit_to_project)

    def set_current_time(self, seconds: float) -> None:
        self.canvas.set_current_time(seconds)
        self.time_label.setText(format_timestamp(seconds))
        self._ensure_playhead_visible()

    def set_selected_item(self, item_id: str) -> None:
        self.canvas.set_selected_item(item_id)

    def fit_to_project(self) -> None:
        duration = self.canvas.project.total_duration()
        if duration <= 0:
            return
        available = max(100, self.scroll.viewport().width() - self.canvas.left_margin - 36)
        pixels_per_second = int(clamp(available / duration, 1, 500))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(pixels_per_second)
        self.zoom_slider.blockSignals(False)
        self.canvas.set_pixels_per_second(pixels_per_second)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self.fit_to_project)

    def set_theme(self, theme: str) -> None:
        self.canvas.set_theme(theme)

    def _time_changed(self, seconds: float) -> None:
        self.time_label.setText(format_timestamp(seconds))
        self.time_changed.emit(seconds)

    def _ensure_playhead_visible(self) -> None:
        x = self.canvas.time_to_x(self.canvas.current_time)
        scrollbar = self.scroll.horizontalScrollBar()
        left = scrollbar.value()
        right = left + self.scroll.viewport().width()
        if x < left + 80:
            scrollbar.setValue(max(0, x - 120))
        elif x > right - 80:
            scrollbar.setValue(x - self.scroll.viewport().width() + 120)
