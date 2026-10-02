from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QElapsedTimer, QPoint, QRect, QSettings, QSize, QTimer, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFontComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QSplitter,
    QSpinBox,
    QStyle,
    QStyledItemDelegate,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
)

from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.dialogs import ExportDialog, ImageEditorDialog, TextImportDialog
from app.exporter import ExportError, export_preview
from app.project_manager import ProjectError, ProjectManager
from app.settings import (
    APP_NAME,
    CANVAS_WIDTH,
    DEFAULT_DURATION,
    MAX_PREVIEW_COLUMNS_1080P,
    MIN_PREVIEW_COLUMNS_1080P,
    MIN_CLIP_DURATION,
    OPENING_ANIMATION_OPTIONS,
    PROJECT_EXTENSION,
    PROJECTS_DIR,
    SUPPORTED_AUDIO_FILTER,
    SUPPORTED_IMAGE_FILTER,
    app_style,
)
from app.utils.time_utils import clamp, format_timestamp
from app.utils.image_utils import ImageCache, draw_image
from app.widgets.asset_panel import AssetPanel
from app.widgets.preview_widget import PreviewWidget
from app.widgets.timeline_widget import TimelineWidget
from app.widgets.transport_controls import TransportControls


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setMinimumWidth(104)
        self.clicked.connect(self._choose_color)
        self._update_swatch()

    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        if color == self._color:
            return
        self._color = color
        self._update_swatch()
        self.color_changed.emit(color)

    def _choose_color(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self, "Choose Color")
        if chosen.isValid():
            self.set_color(chosen.name())

    def _update_swatch(self) -> None:
        color = QColor(self._color)
        foreground = "#111827" if color.lightness() > 150 else "#ffffff"
        self.setText(self._color.upper())
        self.setStyleSheet(
            f"QPushButton {{ background: {self._color}; color: {foreground}; "
            "border: 1px solid #64748b; font-weight: 700; }}"
        )


class ContentOrderDelegate(QStyledItemDelegate):
    BUTTON_SIZE = 30
    BUTTON_GAP = 6

    @classmethod
    def action_rects(cls, rect: QRect) -> tuple[QRect, QRect]:
        top = rect.center().y() - cls.BUTTON_SIZE // 2
        delete_rect = QRect(
            rect.right() - cls.BUTTON_SIZE - 10,
            top,
            cls.BUTTON_SIZE,
            cls.BUTTON_SIZE,
        )
        add_rect = delete_rect.translated(-(cls.BUTTON_SIZE + cls.BUTTON_GAP), 0)
        return add_rect, delete_rect

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        row_rect = option.rect.adjusted(3, 3, -3, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_dark = option.palette.base().color().lightness() < 128
        if is_dark:
            background = QColor("#182d4b") if selected else QColor("#13171c")
            border = QColor("#3b82f6") if selected else QColor(
                "#3a424e" if hovered else "#303640"
            )
            text_color = QColor("#dbeafe") if selected else QColor("#f1f3f5")
            muted_color = QColor("#93b5df") if selected else QColor("#aeb6c2")
        else:
            background = QColor("#eff6ff") if selected else QColor("#f8fafc")
            border = QColor("#93c5fd") if selected else QColor(
                "#b8c3d1" if hovered else "#d9e0e8"
            )
            text_color = QColor("#1d4ed8") if selected else QColor("#172033")
            muted_color = QColor("#52739b") if selected else QColor("#667085")
        painter.setBrush(background)
        painter.setPen(QPen(border, 2 if selected else 1))
        painter.drawRoundedRect(row_rect, 10, 10)

        grip_color = QColor("#3b82f6") if selected else muted_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grip_color)
        center_y = row_rect.center().y()
        for x in (row_rect.left() + 13, row_rect.left() + 18):
            for y in (center_y - 5, center_y, center_y + 5):
                painter.drawEllipse(QPoint(x, y), 1, 1)

        add_rect, delete_rect = self.action_rects(option.rect)
        text_rect = row_rect.adjusted(31, 0, -(72), 0)
        painter.setFont(option.font)
        display_text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        type_text, separator, label_text = display_text.partition("  ·  ")
        type_width = QFontMetrics(option.font).horizontalAdvance(
            f"{type_text}{'  ·  ' if separator else ''}"
        )
        type_rect = QRect(text_rect.x(), text_rect.y(), type_width, text_rect.height())
        painter.setPen(muted_color)
        painter.drawText(
            type_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{type_text}{'  ·  ' if separator else ''}",
        )
        label_rect = text_rect.adjusted(type_width, 0, 0, 0)
        painter.setPen(text_color)
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label_text,
        )

        self._draw_action_button(painter, add_rect, QColor("#2563eb"), False)
        can_delete = bool(option.widget and option.widget.count() > 1)
        delete_color = QColor("#dc2626") if can_delete else QColor("#94a3b8")
        self._draw_action_button(painter, delete_rect, delete_color, True)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(super().sizeHint(option, index).width(), 62)

    @staticmethod
    def _draw_action_button(
        painter: QPainter, rect: QRect, color: QColor, is_delete: bool
    ) -> None:
        fill = QColor(color)
        fill.setAlpha(24)
        painter.setBrush(fill)
        painter.setPen(QPen(color, 1))
        painter.drawRoundedRect(rect, 6, 6)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 2))
        center = rect.center()
        if not is_delete:
            painter.drawLine(center.x() - 5, center.y(), center.x() + 5, center.y())
            painter.drawLine(center.x(), center.y() - 5, center.x(), center.y() + 5)
            return
        painter.drawRect(QRect(center.x() - 4, center.y() - 3, 8, 9))
        painter.drawLine(center.x() - 6, center.y() - 6, center.x() + 6, center.y() - 6)
        painter.drawLine(center.x() - 2, center.y() - 8, center.x() + 2, center.y() - 8)


class ContentOrderList(QListWidget):
    add_requested = Signal(str)
    delete_requested = Signal(str)

    def mousePressEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            add_rect, delete_rect = ContentOrderDelegate.action_rects(
                self.visualRect(index)
            )
            field_id = str(index.data(Qt.ItemDataRole.UserRole) or "")
            if add_rect.contains(event.position().toPoint()):
                self.setCurrentIndex(index)
                self.add_requested.emit(field_id)
                event.accept()
                return
            if delete_rect.contains(event.position().toPoint()):
                self.setCurrentIndex(index)
                if self.count() > 1:
                    self.delete_requested.emit(field_id)
                event.accept()
                return
        super().mousePressEvent(event)


BOX_STYLE_PRESETS: list[dict[str, object]] = [
    {
        "name": "Sport Classic",
        "border_color": "#05070a",
        "text_font_family": "Segoe UI",
        "image_fit": "cover",
        "image_height_percent": 56,
        "roles": {
            "name": {"background_color": "#f45b69", "text_color": "#ffffff"},
            "category": {"background_color": "#050505", "text_color": "#ffffff"},
            "rank": {"background_color": "#fbb10b", "text_color": "#080808"},
            "value": {"background_color": "#087be8", "text_color": "#ffffff"},
        },
    },
    {
        "name": "Neon League",
        "border_color": "#13f2c2",
        "text_font_family": "Bahnschrift",
        "image_fit": "cover",
        "image_height_percent": 58,
        "roles": {
            "name": {"background_color": "#111827", "text_color": "#13f2c2"},
            "category": {"background_color": "#050816", "text_color": "#ffffff"},
            "rank": {"background_color": "#f0f757", "text_color": "#050816"},
            "value": {"background_color": "#7c3aed", "text_color": "#ffffff"},
        },
    },
    {
        "name": "Broadcast Red",
        "border_color": "#111111",
        "text_font_family": "Arial",
        "image_fit": "cover",
        "image_height_percent": 55,
        "roles": {
            "name": {"background_color": "#d90429", "text_color": "#ffffff"},
            "category": {"background_color": "#1f2937", "text_color": "#f8fafc"},
            "rank": {"background_color": "#ffba08", "text_color": "#111111"},
            "value": {"background_color": "#003566", "text_color": "#ffffff"},
        },
    },
    {
        "name": "Clean White",
        "border_color": "#0f172a",
        "text_font_family": "Segoe UI",
        "image_fit": "contain",
        "image_height_percent": 52,
        "roles": {
            "name": {"background_color": "#ffffff", "text_color": "#0f172a"},
            "category": {"background_color": "#e2e8f0", "text_color": "#0f172a"},
            "rank": {"background_color": "#0f172a", "text_color": "#ffffff"},
            "value": {"background_color": "#2563eb", "text_color": "#ffffff"},
        },
    },
    {
        "name": "Gold Table",
        "border_color": "#f59e0b",
        "text_font_family": "Georgia",
        "image_fit": "cover",
        "image_height_percent": 54,
        "roles": {
            "name": {"background_color": "#18181b", "text_color": "#fef3c7"},
            "category": {"background_color": "#78350f", "text_color": "#fef3c7"},
            "rank": {"background_color": "#f59e0b", "text_color": "#111827"},
            "value": {"background_color": "#27272a", "text_color": "#fef3c7"},
        },
    },
    {
        "name": "Ocean Stats",
        "border_color": "#38bdf8",
        "text_font_family": "Verdana",
        "image_fit": "stretch",
        "image_height_percent": 60,
        "roles": {
            "name": {"background_color": "#0369a1", "text_color": "#ffffff"},
            "category": {"background_color": "#0f172a", "text_color": "#bae6fd"},
            "rank": {"background_color": "#22d3ee", "text_color": "#083344"},
            "value": {"background_color": "#0e7490", "text_color": "#ffffff"},
        },
    },
    {
        "name": "Esports Pulse",
        "border_color": "#fb7185",
        "text_font_family": "Impact",
        "image_fit": "cover",
        "image_height_percent": 62,
        "roles": {
            "name": {"background_color": "#be123c", "text_color": "#ffffff"},
            "category": {"background_color": "#111827", "text_color": "#fda4af"},
            "rank": {"background_color": "#a3e635", "text_color": "#1a2e05"},
            "value": {"background_color": "#4c1d95", "text_color": "#ffffff"},
        },
    },
    {
        "name": "Minimal Dark",
        "border_color": "#334155",
        "text_font_family": "Segoe UI",
        "image_fit": "contain",
        "image_height_percent": 50,
        "roles": {
            "name": {"background_color": "#0f172a", "text_color": "#f8fafc"},
            "category": {"background_color": "#1e293b", "text_color": "#cbd5e1"},
            "rank": {"background_color": "#475569", "text_color": "#ffffff"},
            "value": {"background_color": "#020617", "text_color": "#f8fafc"},
        },
    },
    {
        "name": "Carbon Silver",
        "border_color": "#94a3b8",
        "text_font_family": "Bahnschrift",
        "image_fit": "contain",
        "image_height_percent": 56,
        "roles": {
            "name": {"background_color": "#18181b", "text_color": "#fafafa"},
            "category": {"background_color": "#27272a", "text_color": "#d4d4d8"},
            "rank": {"background_color": "#d4d4d8", "text_color": "#18181b"},
            "value": {"background_color": "#3f3f46", "text_color": "#fafafa"},
        },
    },
    {
        "name": "Midnight Blue",
        "border_color": "#60a5fa",
        "text_font_family": "Segoe UI",
        "image_fit": "contain",
        "image_height_percent": 58,
        "roles": {
            "name": {"background_color": "#172554", "text_color": "#eff6ff"},
            "category": {"background_color": "#0f172a", "text_color": "#bfdbfe"},
            "rank": {"background_color": "#60a5fa", "text_color": "#0f172a"},
            "value": {"background_color": "#1e3a8a", "text_color": "#eff6ff"},
        },
    },
    {
        "name": "Cyberpunk Pink",
        "border_color": "#f472b6",
        "text_font_family": "Bahnschrift",
        "image_fit": "cover",
        "image_height_percent": 62,
        "roles": {
            "name": {"background_color": "#2e1065", "text_color": "#f9a8d4"},
            "category": {"background_color": "#09090b", "text_color": "#67e8f9"},
            "rank": {"background_color": "#f472b6", "text_color": "#2e1065"},
            "value": {"background_color": "#164e63", "text_color": "#cffafe"},
        },
    },
    {
        "name": "Arcade Lime",
        "border_color": "#a3e635",
        "text_font_family": "Impact",
        "image_fit": "cover",
        "image_height_percent": 60,
        "roles": {
            "name": {"background_color": "#1a2e05", "text_color": "#d9f99d"},
            "category": {"background_color": "#18181b", "text_color": "#fafafa"},
            "rank": {"background_color": "#a3e635", "text_color": "#1a2e05"},
            "value": {"background_color": "#581c87", "text_color": "#f3e8ff"},
        },
    },
    {
        "name": "Stadium Green",
        "border_color": "#22c55e",
        "text_font_family": "Arial",
        "image_fit": "cover",
        "image_height_percent": 58,
        "roles": {
            "name": {"background_color": "#166534", "text_color": "#ffffff"},
            "category": {"background_color": "#052e16", "text_color": "#bbf7d0"},
            "rank": {"background_color": "#fde047", "text_color": "#052e16"},
            "value": {"background_color": "#14532d", "text_color": "#f0fdf4"},
        },
    },
    {
        "name": "Racing Orange",
        "border_color": "#fb923c",
        "text_font_family": "Bahnschrift",
        "image_fit": "cover",
        "image_height_percent": 60,
        "roles": {
            "name": {"background_color": "#c2410c", "text_color": "#ffffff"},
            "category": {"background_color": "#18181b", "text_color": "#fed7aa"},
            "rank": {"background_color": "#fb923c", "text_color": "#18181b"},
            "value": {"background_color": "#431407", "text_color": "#fff7ed"},
        },
    },
    {
        "name": "Royal Purple",
        "border_color": "#c4b5fd",
        "text_font_family": "Georgia",
        "image_fit": "cover",
        "image_height_percent": 54,
        "roles": {
            "name": {"background_color": "#5b21b6", "text_color": "#ffffff"},
            "category": {"background_color": "#2e1065", "text_color": "#ddd6fe"},
            "rank": {"background_color": "#fde68a", "text_color": "#2e1065"},
            "value": {"background_color": "#4c1d95", "text_color": "#f5f3ff"},
        },
    },
    {
        "name": "Sunset Coral",
        "border_color": "#fdba74",
        "text_font_family": "Trebuchet MS",
        "image_fit": "cover",
        "image_height_percent": 58,
        "roles": {
            "name": {"background_color": "#9f1239", "text_color": "#fff1f2"},
            "category": {"background_color": "#4c0519", "text_color": "#fecdd3"},
            "rank": {"background_color": "#fdba74", "text_color": "#4c0519"},
            "value": {"background_color": "#9a3412", "text_color": "#fff7ed"},
        },
    },
    {
        "name": "Forest Cream",
        "border_color": "#365314",
        "text_font_family": "Georgia",
        "image_fit": "contain",
        "image_height_percent": 52,
        "roles": {
            "name": {"background_color": "#fefce8", "text_color": "#365314"},
            "category": {"background_color": "#ecfccb", "text_color": "#3f6212"},
            "rank": {"background_color": "#365314", "text_color": "#fefce8"},
            "value": {"background_color": "#d9f99d", "text_color": "#1a2e05"},
        },
    },
    {
        "name": "Sandstone",
        "border_color": "#a16207",
        "text_font_family": "Verdana",
        "image_fit": "contain",
        "image_height_percent": 52,
        "roles": {
            "name": {"background_color": "#fffbeb", "text_color": "#78350f"},
            "category": {"background_color": "#fef3c7", "text_color": "#78350f"},
            "rank": {"background_color": "#92400e", "text_color": "#fffbeb"},
            "value": {"background_color": "#fde68a", "text_color": "#451a03"},
        },
    },
    {
        "name": "Pastel Lavender",
        "border_color": "#8b5cf6",
        "text_font_family": "Segoe UI",
        "image_fit": "contain",
        "image_height_percent": 50,
        "roles": {
            "name": {"background_color": "#f5f3ff", "text_color": "#4c1d95"},
            "category": {"background_color": "#ede9fe", "text_color": "#5b21b6"},
            "rank": {"background_color": "#c4b5fd", "text_color": "#2e1065"},
            "value": {"background_color": "#fae8ff", "text_color": "#701a75"},
        },
    },
    {
        "name": "Rose Quartz",
        "border_color": "#be185d",
        "text_font_family": "Segoe UI",
        "image_fit": "contain",
        "image_height_percent": 52,
        "roles": {
            "name": {"background_color": "#fff1f2", "text_color": "#9f1239"},
            "category": {"background_color": "#fce7f3", "text_color": "#831843"},
            "rank": {"background_color": "#be185d", "text_color": "#ffffff"},
            "value": {"background_color": "#fecdd3", "text_color": "#881337"},
        },
    },
    {
        "name": "Ice Blue",
        "border_color": "#0284c7",
        "text_font_family": "Verdana",
        "image_fit": "contain",
        "image_height_percent": 54,
        "roles": {
            "name": {"background_color": "#f0f9ff", "text_color": "#0c4a6e"},
            "category": {"background_color": "#e0f2fe", "text_color": "#075985"},
            "rank": {"background_color": "#0369a1", "text_color": "#ffffff"},
            "value": {"background_color": "#bae6fd", "text_color": "#082f49"},
        },
    },
    {
        "name": "Retro Terminal",
        "border_color": "#4ade80",
        "text_font_family": "Consolas",
        "image_fit": "contain",
        "image_height_percent": 50,
        "roles": {
            "name": {"background_color": "#052e16", "text_color": "#4ade80"},
            "category": {"background_color": "#09090b", "text_color": "#86efac"},
            "rank": {"background_color": "#4ade80", "text_color": "#052e16"},
            "value": {"background_color": "#14532d", "text_color": "#bbf7d0"},
        },
    },
    {
        "name": "Vintage Paper",
        "border_color": "#78716c",
        "text_font_family": "Georgia",
        "image_fit": "contain",
        "image_height_percent": 50,
        "roles": {
            "name": {"background_color": "#f5f5f4", "text_color": "#44403c"},
            "category": {"background_color": "#e7e5e4", "text_color": "#57534e"},
            "rank": {"background_color": "#78350f", "text_color": "#fef3c7"},
            "value": {"background_color": "#d6d3d1", "text_color": "#292524"},
        },
    },
    {
        "name": "Monochrome",
        "border_color": "#171717",
        "text_font_family": "Arial",
        "image_fit": "contain",
        "image_height_percent": 54,
        "roles": {
            "name": {"background_color": "#fafafa", "text_color": "#171717"},
            "category": {"background_color": "#e5e5e5", "text_color": "#262626"},
            "rank": {"background_color": "#171717", "text_color": "#fafafa"},
            "value": {"background_color": "#404040", "text_color": "#fafafa"},
        },
    },
]
BOX_STYLE_PRESETS_BY_NAME = {
    str(preset["name"]): preset for preset in BOX_STYLE_PRESETS
}


class BoxStylePreview(QWidget):
    image_clicked = Signal(str)
    field_selected = Signal(str)
    field_reorder_requested = Signal(str, str, bool)

    def __init__(self, item: ComparisonItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item = item
        self.image_fit = "cover"
        self.image_height_percent = 56
        self.border_color = "#05070a"
        self.text_font_family = "Segoe UI"
        self.text_font_size = 0
        self.columns = MIN_PREVIEW_COLUMNS_1080P
        self.field_styles: dict[str, dict[str, str]] = {}
        self._image_cache = ImageCache()
        self._field_regions: list[tuple[QRect, str, str]] = []
        self._press_position: QPoint | None = None
        self._pressed_field_id = ""
        self._pressed_field_type = ""
        self._dragging_field_id = ""
        self._drop_target: tuple[str, bool] | None = None
        self._selected_field_id = ""
        self.setMouseTracking(True)
        self.setToolTip(
            "Drag any block to reorder it. Click an image to crop or reposition it."
        )
        self.setFixedSize(330, 557)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            for region, field_id, field_type in self._field_regions:
                if region.contains(event.position().toPoint()):
                    self._press_position = event.position().toPoint()
                    self._pressed_field_id = field_id
                    self._pressed_field_type = field_type
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        position = event.position().toPoint()
        if (
            self._press_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (position - self._press_position).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._dragging_field_id = self._pressed_field_id
        if self._dragging_field_id:
            self._drop_target = None
            for region, field_id, _field_type in self._field_regions:
                if region.contains(position) and field_id != self._dragging_field_id:
                    self._drop_target = (field_id, position.y() >= region.center().y())
                    break
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return
        if any(region.contains(position) for region, _field_id, _type in self._field_regions):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed_field_id:
            if self._dragging_field_id and self._drop_target is not None:
                target_id, drop_after = self._drop_target
                self.field_reorder_requested.emit(
                    self._dragging_field_id, target_id, drop_after
                )
            elif not self._dragging_field_id:
                self.field_selected.emit(self._pressed_field_id)
                if self._pressed_field_type == "image":
                    self.image_clicked.emit(self._pressed_field_id)
            self._reset_drag_state()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _reset_drag_state(self) -> None:
        self._press_position = None
        self._pressed_field_id = ""
        self._pressed_field_type = ""
        self._dragging_field_id = ""
        self._drop_target = None
        self.unsetCursor()
        self.update()

    def set_style(
        self,
        image_fit: str,
        image_height_percent: int,
        border_color: str,
        text_font_family: str,
        field_styles: dict[str, dict[str, str]],
        text_font_size: int = 0,
        columns: int = MIN_PREVIEW_COLUMNS_1080P,
    ) -> None:
        self.image_fit = image_fit
        self.image_height_percent = image_height_percent
        self.border_color = border_color
        self.text_font_family = text_font_family
        self.field_styles = field_styles
        self.text_font_size = text_font_size
        self.columns = columns
        self.update()

    def set_selected_field(self, field_id: str) -> None:
        self._selected_field_id = field_id
        self.update()

    def paintEvent(self, event) -> None:
        self._field_regions = []
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b0d10"))
        card = self.rect().adjusted(8, 8, -8, -8)
        fields = self.item.display_fields()
        image_fields = [field for field in fields if field.get("type") == "image"]
        content_fields = [
            field for field in fields if field.get("type") != "image"
        ]
        total_image_height = (
            int(card.height() * self.image_height_percent / 100) if image_fields else 0
        )
        if not content_fields:
            total_image_height = card.height()
        total_text_height = card.height() - total_image_height
        text_weights = [
            self._style_int(
                self.field_styles.get(str(field_data.get("id", "")), {}),
                "height_weight", 100, 25, 400,
            )
            for field_data in content_fields
        ]
        image_weights = [
            self._style_int(
                self.field_styles.get(str(field_data.get("id", "")), {}),
                "height_weight", 100, 25, 400,
            )
            for field_data in image_fields
        ]
        remaining_image_pixels = total_image_height
        remaining_image_weight = sum(image_weights)
        remaining_text_pixels = total_text_height
        remaining_text_weight = sum(text_weights)
        row_y = card.y()
        image_index = 0
        content_index = 0
        for field_data in fields:
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
            row = QRect(card.x(), row_y, card.width(), row_height)
            self._field_regions.append((row, field_id, field_type))
            if field_type == "image":
                draw_image(
                    painter,
                    self._image_cache,
                    str(field_data.get("value", "")),
                    row,
                    self.image_fit,
                    self.item.image_transforms.get(field_id),
                    self.item.image_crop_x,
                    self.item.image_crop_y,
                )
                row_y += row_height
                remaining_image_pixels -= row_height
                remaining_image_weight -= image_weight
                image_index += 1
                continue

            role = self._preview_field_role(field_data, content_index)
            style = self.field_styles.get(str(field_data.get("id", "")), {})
            painter.fillRect(
                row, QColor(style.get("background_color", "#111827"))
            )
            font_size = 15 if role in {"name", "rank"} else 13
            padding = self._style_int(style, "padding", 14, 0, 64)
            scale = card.width() / (CANVAS_WIDTH / self.columns)
            preview_padding = max(2, round(padding * scale))
            target = row.adjusted(preview_padding, 2, -preview_padding, -2)
            horizontal = {
                "left": Qt.AlignmentFlag.AlignLeft,
                "right": Qt.AlignmentFlag.AlignRight,
            }.get(style.get("alignment", "center"), Qt.AlignmentFlag.AlignHCenter)
            flags = horizontal | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
            weight_value = self._style_int(style, "font_weight", 700, 100, 900)
            weight_value = min((100, 200, 300, 400, 500, 600, 700, 800, 900), key=lambda value: abs(value - weight_value))
            font_weight = QFont.Weight(weight_value)
            custom_size = self._style_int(style, "font_size", 0, 0, 120)
            if custom_size:
                font_size = max(1, round(custom_size * scale))
                minimum_size = max(1, round(min(12, custom_size) * scale))
            elif self.text_font_size:
                size = self.text_font_size if role in {"name", "rank"} else max(
                    1, int(self.text_font_size * 0.88)
                )
                font_size = max(1, round(size * scale))
                minimum_size = max(1, round(min(12, size) * scale))
            else:
                minimum_size = 6
            if self.text_font_size or custom_size:
                while font_size > minimum_size:
                    font = QFont(self.text_font_family, font_size, font_weight)
                    bounds = QFontMetrics(font).boundingRect(
                        target, int(flags), str(field_data.get("value", ""))
                    )
                    if bounds.width() <= target.width() and bounds.height() <= target.height():
                        break
                    font_size -= 1
            painter.setFont(QFont(self.text_font_family, font_size, font_weight))
            outline_width = max(
                0,
                round(self._style_int(style, "outline_width", 0, 0, 8) * scale),
            )
            text = str(field_data.get("value", ""))
            if outline_width:
                painter.setPen(QColor(style.get("outline_color", "#000000")))
                for distance in range(1, outline_width + 1):
                    for dx, dy in (
                        (-distance, -distance), (0, -distance), (distance, -distance),
                        (-distance, 0), (distance, 0),
                        (-distance, distance), (0, distance), (distance, distance),
                    ):
                        painter.drawText(target.translated(dx, dy), flags, text)
            painter.setPen(QColor(style.get("text_color", "#ffffff")))
            painter.drawText(
                target,
                flags,
                text,
            )
            border_width = max(
                0,
                round(self._style_int(style, "border_width", 0, 0, 12) * scale),
            )
            if border_width:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(style.get("border_color", "#000000")), border_width))
                inset = max(1, border_width // 2)
                painter.drawRect(row.adjusted(inset, inset, -inset, -inset))
            row_y += row_height
            remaining_text_pixels -= row_height
            remaining_text_weight -= weight
            content_index += 1

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(self.border_color), 3))
        painter.drawRect(card.adjusted(1, 1, -2, -2))
        if self._selected_field_id and not self._dragging_field_id:
            for region, field_id, _field_type in self._field_regions:
                if field_id == self._selected_field_id:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor("#60a5fa"), 2))
                    painter.drawRect(region.adjusted(2, 2, -3, -3))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor("#dbeafe"))
                    center_y = region.center().y()
                    for x in (region.left() + 8, region.left() + 13):
                        for y in (center_y - 5, center_y, center_y + 5):
                            painter.drawEllipse(QPoint(x, y), 1, 1)
                    break
        if self._dragging_field_id:
            for region, field_id, _field_type in self._field_regions:
                if field_id == self._dragging_field_id:
                    painter.fillRect(region, QColor(59, 130, 246, 55))
                    painter.setPen(QPen(QColor("#60a5fa"), 2))
                    painter.drawRect(region.adjusted(1, 1, -2, -2))
                    break
            if self._drop_target is not None:
                target_id, drop_after = self._drop_target
                for region, field_id, _field_type in self._field_regions:
                    if field_id == target_id:
                        y = region.bottom() if drop_after else region.top()
                        painter.setPen(QPen(QColor("#3b82f6"), 4))
                        painter.drawLine(card.left(), y, card.right(), y)
                        break
        painter.end()

    def _preview_field_role(self, field_data: dict[str, str], index: int) -> str:
        role = str(field_data.get("role", ""))
        if role in {"name", "category", "rank", "value"}:
            return role
        if field_data.get("type") == "name":
            return "name"
        if field_data.get("type") == "number":
            return "rank"
        return "category" if index < 2 else "value"

    @staticmethod
    def _style_int(
        style: dict[str, str], key: str, default: int, minimum: int, maximum: int
    ) -> int:
        try:
            value = int(style.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))


class ProjectSettingsDialog(QDialog):
    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._item_count = len(project.comparison_items)
        self.setWindowTitle("Project Settings")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        general_page = QWidget()
        form = QFormLayout(general_page)
        self.name_edit = QLineEdit(project.name)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "60"])
        self.fps_combo.setCurrentText(str(project.fps))
        self.preview_columns_spin = QSpinBox()
        self.preview_columns_spin.setRange(MIN_PREVIEW_COLUMNS_1080P, MAX_PREVIEW_COLUMNS_1080P)
        self.preview_columns_spin.setValue(project.preview_max_columns)
        self.opening_animation_combo = QComboBox()
        for label, value in OPENING_ANIMATION_OPTIONS:
            self.opening_animation_combo.addItem(label, value)
        self.opening_animation_combo.setCurrentIndex(
            max(0, self.opening_animation_combo.findData(project.opening_animation))
        )
        self.item_duration_spin = QDoubleSpinBox()
        self.item_duration_spin.setRange(MIN_CLIP_DURATION, 120.0)
        self.item_duration_spin.setDecimals(3)
        self.item_duration_spin.setSingleStep(0.25)
        self.item_duration_spin.setValue(project.item_fixed_duration)
        form.addRow("Project Name", self.name_edit)
        form.addRow("Resolution", QLabel(f"{project.width} x {project.height}"))
        form.addRow("FPS", self.fps_combo)
        form.addRow("Preview Columns", self.preview_columns_spin)
        form.addRow("Opening Animation", self.opening_animation_combo)
        form.addRow("Box Duration", self.item_duration_spin)
        self.animation_length_label = QLabel()
        form.addRow("Animation Length", self.animation_length_label)
        self.item_duration_spin.valueChanged.connect(self._update_animation_length)
        self._update_animation_length(self.item_duration_spin.value())
        tabs.addTab(general_page, "General")

        design_page = QWidget()
        design_form = QFormLayout(design_page)
        self.canvas_color_button = ColorButton(project.canvas_background_color)
        self.border_color_button = ColorButton(project.card_border_color)
        self.text_font_combo = QFontComboBox()
        self.text_font_combo.setCurrentFont(QFont(project.text_font_family))
        design_form.addRow("Canvas Background", self.canvas_color_button)
        design_form.addRow("Box Border", self.border_color_button)
        design_form.addRow("Text Font", self.text_font_combo)

        self.band_color_buttons: dict[str, tuple[ColorButton, ColorButton]] = {}
        band_settings = (
            ("name", "Title", project.name_background_color, project.name_text_color),
            (
                "category",
                "Category",
                project.category_background_color,
                project.category_text_color,
            ),
            ("rank", "Rank / Score", project.rank_background_color, project.rank_text_color),
            ("value", "Value", project.value_background_color, project.value_text_color),
        )
        for key, label, background, text in band_settings:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            background_button = ColorButton(background)
            text_button = ColorButton(text)
            row_layout.addWidget(QLabel("Background"))
            row_layout.addWidget(background_button)
            row_layout.addSpacing(8)
            row_layout.addWidget(QLabel("Text"))
            row_layout.addWidget(text_button)
            row_layout.addStretch(1)
            design_form.addRow(label, row)
            self.band_color_buttons[key] = (background_button, text_button)
        design_form.addRow("Image Fit", QLabel(project.image_fit.title()))
        tabs.addTab(design_page, "Box Design")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to(self, project: Project) -> None:
        project.name = self.name_edit.text().strip() or "Untitled Project"
        project.fps = int(self.fps_combo.currentText())
        project.preview_max_columns = int(self.preview_columns_spin.value())
        project.opening_animation = str(self.opening_animation_combo.currentData())
        project.item_fixed_duration = float(self.item_duration_spin.value())
        project.canvas_background_color = self.canvas_color_button.color()
        project.card_border_color = self.border_color_button.color()
        project.text_font_family = self.text_font_combo.currentFont().family()
        for key, (background_button, text_button) in self.band_color_buttons.items():
            setattr(project, f"{key}_background_color", background_button.color())
            setattr(project, f"{key}_text_color", text_button.color())
        project.field_styles.clear()
        project.apply_fixed_item_timing()

    def _update_animation_length(self, box_duration: float) -> None:
        duration = (self._item_count + 1) * box_duration if self._item_count else 0.0
        self.animation_length_label.setText(format_timestamp(duration))


class BoxCustomizationDialog(QDialog):
    STYLE_KEYS = (
        "card_border_color",
        "name_background_color",
        "name_text_color",
        "category_background_color",
        "category_text_color",
        "rank_background_color",
        "rank_text_color",
        "value_background_color",
        "value_text_color",
    )

    def __init__(
        self,
        project: Project,
        item: ComparisonItem,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.item = item
        self._image_item = ComparisonItem.from_dict(item.to_dict())
        self._images_changed = False
        self.preferences = QSettings("DataCompareTools", "DataComparisonVideoMaker")
        self.custom_presets = self._load_custom_presets()
        self.setObjectName("BoxCustomizationDialog")
        self.setWindowTitle("Customize All Boxes")
        self.setMinimumSize(1100, 700)
        self.resize(1320, 840)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)

        header = QWidget()
        header.setObjectName("DesignerHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.setSpacing(10)
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        dialog_title = QLabel("Box designer")
        dialog_title.setObjectName("DesignerTitle")
        dialog_subtitle = QLabel(
            "Arrange content, edit the selected block, and preview every change live."
        )
        dialog_subtitle.setObjectName("DesignerSubtitle")
        header_text.addWidget(dialog_title)
        header_text.addWidget(dialog_subtitle)
        scope_badge = QLabel("ALL BOXES")
        scope_badge.setObjectName("DesignerBadge")
        header_layout.addLayout(header_text)
        header_layout.addStretch(1)
        header_layout.addWidget(scope_badge)
        layout.addWidget(header)

        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setObjectName("DesignerSplitter")
        content_splitter.setHandleWidth(8)
        content_splitter.setChildrenCollapsible(False)

        controls_scroll = QScrollArea()
        controls_scroll.setObjectName("DesignerInspectorScroll")
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_widget = QWidget()
        controls_widget.setObjectName("DesignerInspector")
        controls_layout = QVBoxLayout(controls_widget)
        controls_layout.setContentsMargins(8, 4, 12, 8)
        controls_layout.setSpacing(12)

        layout_group = QGroupBox("Box layout")
        layout_group.setObjectName("DesignerSection")
        form = QFormLayout(layout_group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.columns_combo = QComboBox()
        for columns in range(MIN_PREVIEW_COLUMNS_1080P, MAX_PREVIEW_COLUMNS_1080P + 1):
            self.columns_combo.addItem(f"{columns} columns", columns)
        self.columns_combo.setCurrentIndex(
            max(0, self.columns_combo.findData(project.preview_max_columns))
        )
        form.addRow("Display layout", self.columns_combo)

        self.box_size_label = QLabel()
        form.addRow("Box size", self.box_size_label)

        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        preset_layout.setSpacing(5)
        self.preset_combo = QComboBox()
        self.preset_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.preset_combo.setMinimumContentsLength(12)
        self.apply_preset_button = QPushButton("Apply")
        self.apply_preset_button.setObjectName("PresetAction")
        self.save_preset_button = QPushButton("Save")
        self.save_preset_button.setObjectName("PresetAction")
        self.save_preset_button.setToolTip("Save these settings as a custom preset")
        self.delete_preset_button = QPushButton("Delete")
        self.delete_preset_button.setObjectName("PresetAction")
        self.delete_preset_button.setToolTip("Delete the selected custom preset")
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(self.apply_preset_button)
        preset_layout.addWidget(self.save_preset_button)
        preset_layout.addWidget(self.delete_preset_button)
        form.addRow("Preset", preset_row)
        self._populate_preset_combo()

        slider_row = QWidget()
        slider_layout = QHBoxLayout(slider_row)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        self.image_height_slider = QSlider(Qt.Orientation.Horizontal)
        self.image_height_slider.setRange(35, 75)
        self.image_height_slider.setSingleStep(1)
        self.image_height_value = QLabel()
        self.image_height_value.setMinimumWidth(46)
        slider_layout.addWidget(self.image_height_slider, 1)
        slider_layout.addWidget(self.image_height_value)
        form.addRow("Images total height", slider_row)

        self.image_fit_combo = QComboBox()
        self.image_fit_combo.addItem("Cover - crop to fill", "cover")
        self.image_fit_combo.addItem("Contain - show full image", "contain")
        self.image_fit_combo.addItem("Stretch - resize to box", "stretch")
        form.addRow("Image fit", self.image_fit_combo)

        self.text_font_combo = QFontComboBox()
        self.text_font_combo.setCurrentFont(QFont(project.text_font_family))
        form.addRow("Text font", self.text_font_combo)

        self.text_font_size_spin = QSpinBox()
        self.text_font_size_spin.setRange(0, 120)
        self.text_font_size_spin.setSpecialValueText("Auto")
        self.text_font_size_spin.setSuffix(" pt")
        self.text_font_size_spin.setValue(project.text_font_size)
        self.text_font_size_spin.setToolTip(
            "Text size at 1080p. Auto sizes text to the box width. "
            "Long text shrinks to fit; category and value text are slightly smaller."
        )
        form.addRow("Font size", self.text_font_size_spin)

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(MIN_CLIP_DURATION, 24 * 60 * 60)
        self.duration_spin.setDecimals(3)
        self.duration_spin.setSingleStep(0.1)
        self.duration_spin.setSuffix(" sec")
        self.duration_spin.setValue(project.item_fixed_duration)
        form.addRow("Box duration", self.duration_spin)

        self.border_color_button = ColorButton(project.card_border_color)
        form.addRow("Box border", self.border_color_button)
        controls_layout.addWidget(layout_group)

        order_group = QGroupBox("Content order")
        order_group.setObjectName("DesignerSection")
        order_layout = QVBoxLayout(order_group)
        order_hint = QLabel(
            "Drag images and text here—or directly on the preview—to build the box."
        )
        order_hint.setObjectName("DesignerHint")
        order_hint.setWordWrap(True)
        order_layout.addWidget(order_hint)
        self.field_order_list = ContentOrderList()
        self.field_order_list.setObjectName("DesignerOrderList")
        self.field_order_list.setMouseTracking(True)
        self.field_order_list.setItemDelegate(ContentOrderDelegate(self.field_order_list))
        self.field_order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.field_order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.field_order_list.setDragDropOverwriteMode(False)
        self.field_order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.field_order_list.setMinimumHeight(150)
        self.field_order_list.setMaximumHeight(220)

        self.field_styles: dict[str, dict[str, str]] = {}
        self.field_roles: dict[str, str] = {}
        self.field_types: dict[str, str] = {}
        self._new_field_sources: dict[str, str] = {}
        content_index = 0
        for field_data in item.display_fields():
            field_id = str(field_data.get("id", ""))
            field_type = str(field_data.get("type", "text"))
            self.field_types[field_id] = field_type
            saved_style = project.field_styles.get(field_id, {})
            if field_type == "image":
                self.field_styles[field_id] = {
                    "height_weight": str(
                        self._bounded_int(
                            saved_style.get("height_weight"), 100, 25, 400
                        )
                    )
                }
            else:
                role = self._field_role(field_data, content_index)
                self.field_roles[field_id] = role
                self.field_styles[field_id] = self._complete_field_style(
                    saved_style,
                    getattr(project, f"{role}_background_color"),
                    getattr(project, f"{role}_text_color"),
                )
                content_index += 1
            type_label = "IMAGE" if field_type == "image" else "TEXT"
            list_item = QListWidgetItem(
                f"{type_label}  ·  {str(field_data.get('label') or 'Input')}"
            )
            list_item.setData(Qt.ItemDataRole.UserRole, field_id)
            list_item.setToolTip("Drag to reorder; select to edit this band's style")
            self.field_order_list.addItem(list_item)
        order_layout.addWidget(self.field_order_list)
        controls_layout.addWidget(order_group)

        self.content_group = QGroupBox("Selected content")
        self.content_group.setObjectName("DesignerSection")
        content_form = QFormLayout(self.content_group)
        content_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.field_label_edit = QLineEdit()
        self.field_value_edit = QLineEdit()
        self.field_browse_button = QPushButton("Choose image…")
        self.image_height_label = QLabel("Selected image height")
        self.image_height_spin = QSpinBox()
        self.image_height_spin.setRange(25, 400)
        self.image_height_spin.setSuffix(" %")
        self.image_height_spin.setToolTip(
            "Relative height for this image only. 200% makes it twice the height of a 100% image."
        )
        content_form.addRow("Label", self.field_label_edit)
        content_form.addRow("Value", self.field_value_edit)
        content_form.addRow("", self.field_browse_button)
        content_form.addRow(self.image_height_label, self.image_height_spin)
        controls_layout.addWidget(self.content_group)

        self.style_group = QGroupBox("Selected text band")
        self.style_group.setObjectName("DesignerSection")
        style_form = QFormLayout(self.style_group)
        style_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.band_background_button = ColorButton("#111827")
        self.band_text_button = ColorButton("#ffffff")
        self.band_outline_button = ColorButton("#000000")
        self.band_border_button = ColorButton("#000000")
        self.band_outline_width_spin = QSpinBox()
        self.band_outline_width_spin.setRange(0, 8)
        self.band_outline_width_spin.setSuffix(" px")
        self.band_outline_width_spin.setSpecialValueText("None")
        self.band_border_width_spin = QSpinBox()
        self.band_border_width_spin.setRange(0, 12)
        self.band_border_width_spin.setSuffix(" px")
        self.band_border_width_spin.setSpecialValueText("None")
        self.band_alignment_combo = QComboBox()
        self.band_alignment_combo.addItem("Left", "left")
        self.band_alignment_combo.addItem("Center", "center")
        self.band_alignment_combo.addItem("Right", "right")
        self.band_font_weight_combo = QComboBox()
        for label, value in (
            ("Regular", 400), ("Medium", 500), ("Semi-bold", 600),
            ("Bold", 700), ("Extra bold", 800), ("Black", 900),
        ):
            self.band_font_weight_combo.addItem(label, value)
        self.band_font_size_spin = QSpinBox()
        self.band_font_size_spin.setRange(0, 120)
        self.band_font_size_spin.setSpecialValueText("Use global")
        self.band_font_size_spin.setSuffix(" pt")
        self.band_height_spin = QSpinBox()
        self.band_height_spin.setRange(25, 400)
        self.band_height_spin.setSuffix(" %")
        self.band_height_spin.setToolTip(
            "Relative height compared with other text bands; 100% is the default."
        )
        self.band_padding_spin = QSpinBox()
        self.band_padding_spin.setRange(0, 64)
        self.band_padding_spin.setSuffix(" px")
        style_form.addRow("Background", self.band_background_button)
        style_form.addRow("Text", self.band_text_button)
        style_form.addRow("Text outline", self.band_outline_button)
        style_form.addRow("Outline width", self.band_outline_width_spin)
        style_form.addRow("Row border", self.band_border_button)
        style_form.addRow("Border width", self.band_border_width_spin)
        style_form.addRow("Alignment", self.band_alignment_combo)
        style_form.addRow("Font weight", self.band_font_weight_combo)
        style_form.addRow("Font size", self.band_font_size_spin)
        style_form.addRow("Relative height", self.band_height_spin)
        style_form.addRow("Horizontal padding", self.band_padding_spin)
        controls_layout.addWidget(self.style_group)
        controls_layout.addStretch(1)
        controls_scroll.setWidget(controls_widget)
        content_splitter.addWidget(controls_scroll)

        preview_panel = QWidget()
        preview_panel.setObjectName("DesignerPreviewPanel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(22, 20, 22, 18)
        preview_title = QLabel("Live preview")
        preview_title.setObjectName("DesignerPreviewTitle")
        self.box_preview = BoxStylePreview(self._image_item)
        self.box_preview.image_clicked.connect(self._edit_image)
        self.box_preview.field_selected.connect(self._preview_field_selected)
        self.box_preview.field_reorder_requested.connect(
            self._preview_field_reorder_requested
        )
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.box_preview, 0, Qt.AlignmentFlag.AlignHCenter)
        preview_help = QLabel(
            "Drag any image or text block to a new position. Click an image to crop or reposition it."
        )
        preview_help.setObjectName("DesignerHint")
        preview_help.setWordWrap(True)
        preview_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_help)
        preview_layout.addStretch(1)
        content_splitter.addWidget(preview_panel)
        content_splitter.setStretchFactor(0, 3)
        content_splitter.setStretchFactor(1, 2)
        content_splitter.setSizes([780, 480])
        layout.addWidget(content_splitter, 1)

        footer = QWidget()
        footer.setObjectName("DesignerFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(2, 10, 2, 0)
        footer_note = QLabel("Changes are applied to every box in this project.")
        footer_note.setObjectName("DesignerHint")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        footer_layout.addWidget(footer_note)
        footer_layout.addStretch(1)
        footer_layout.addWidget(buttons)
        layout.addWidget(footer)

        self.columns_combo.currentIndexChanged.connect(self._load_values)
        self.image_height_slider.valueChanged.connect(
            self._image_height_changed
        )
        self.image_fit_combo.currentIndexChanged.connect(self._update_preview)
        self.text_font_combo.currentFontChanged.connect(self._update_preview)
        self.text_font_size_spin.valueChanged.connect(self._update_preview)
        self.apply_preset_button.clicked.connect(self._apply_selected_preset)
        self.save_preset_button.clicked.connect(self._save_custom_preset)
        self.delete_preset_button.clicked.connect(self._delete_custom_preset)
        self.border_color_button.color_changed.connect(self._update_preview)
        self.field_order_list.itemSelectionChanged.connect(self._load_selected_field_style)
        self.field_order_list.model().rowsMoved.connect(self._field_order_changed)
        self.field_order_list.add_requested.connect(self._add_content_below)
        self.field_order_list.delete_requested.connect(self._remove_selected_content)
        self._loading_field_content = False
        self.field_label_edit.textEdited.connect(self._selected_field_content_changed)
        self.field_value_edit.textEdited.connect(self._selected_field_content_changed)
        self.field_browse_button.clicked.connect(self._browse_selected_image)
        self.image_height_spin.valueChanged.connect(self._selected_image_height_changed)
        self._loading_field_style = False
        self.band_background_button.color_changed.connect(self._selected_field_style_changed)
        self.band_text_button.color_changed.connect(self._selected_field_style_changed)
        self.band_outline_button.color_changed.connect(self._selected_field_style_changed)
        self.band_border_button.color_changed.connect(self._selected_field_style_changed)
        self.band_outline_width_spin.valueChanged.connect(self._selected_field_style_changed)
        self.band_border_width_spin.valueChanged.connect(self._selected_field_style_changed)
        self.band_alignment_combo.currentIndexChanged.connect(self._selected_field_style_changed)
        self.band_font_weight_combo.currentIndexChanged.connect(self._selected_field_style_changed)
        self.band_font_size_spin.valueChanged.connect(self._selected_field_style_changed)
        self.band_height_spin.valueChanged.connect(self._selected_field_style_changed)
        self.band_padding_spin.valueChanged.connect(self._selected_field_style_changed)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if self.field_order_list.count():
            self.field_order_list.setCurrentRow(0)
        self._load_values()

    def _populate_preset_combo(self, selected_data: str = "") -> None:
        current_data = selected_data or str(self.preset_combo.currentData() or "")
        self.preset_combo.clear()
        for preset in BOX_STYLE_PRESETS:
            name = str(preset["name"])
            self.preset_combo.addItem(name, f"builtin:{name}")
        if self.custom_presets:
            self.preset_combo.insertSeparator(self.preset_combo.count())
            for name in sorted(self.custom_presets):
                self.preset_combo.addItem(f"{name} (Custom)", f"custom:{name}")
        if current_data:
            index = self.preset_combo.findData(current_data)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)

    def _load_custom_presets(self) -> dict[str, dict[str, object]]:
        raw_value = self.preferences.value("box_style_presets", "{}")
        try:
            parsed = json.loads(str(raw_value or "{}"))
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        presets: dict[str, dict[str, object]] = {}
        for name, preset in parsed.items():
            if isinstance(preset, dict):
                presets[str(name)] = self._normalize_preset(preset)
        return presets

    def _save_custom_presets_to_preferences(self) -> None:
        self.preferences.setValue(
            "box_style_presets",
            json.dumps(self.custom_presets, sort_keys=True),
        )

    def _normalize_preset(self, preset: dict[str, object]) -> dict[str, object]:
        fit = str(preset.get("image_fit") or "cover")
        if fit not in {"cover", "contain", "stretch"}:
            fit = "cover"
        try:
            image_height = int(preset.get("image_height_percent") or 56)
        except (TypeError, ValueError):
            image_height = 56
        try:
            font_size = max(0, min(120, int(preset.get("text_font_size") or 0)))
        except (TypeError, ValueError):
            font_size = 0
        roles = preset.get("roles")
        normalized_roles: dict[str, dict[str, str]] = {}
        if isinstance(roles, dict):
            for role, style in roles.items():
                if not isinstance(style, dict):
                    continue
                normalized_roles[str(role)] = {
                    "background_color": self._valid_color(
                        style.get("background_color"), "#111827"
                    ),
                    "text_color": self._valid_color(style.get("text_color"), "#ffffff"),
                    "outline_color": self._valid_color(
                        style.get("outline_color"), "#000000"
                    ),
                    "outline_width": str(self._bounded_int(style.get("outline_width"), 0, 0, 8)),
                    "border_color": self._valid_color(
                        style.get("border_color"), "#000000"
                    ),
                    "border_width": str(self._bounded_int(style.get("border_width"), 0, 0, 12)),
                    "alignment": (
                        str(style.get("alignment"))
                        if str(style.get("alignment")) in {"left", "center", "right"}
                        else "center"
                    ),
                    "font_size": str(self._bounded_int(style.get("font_size"), 0, 0, 120)),
                    "height_weight": str(
                        self._bounded_int(style.get("height_weight"), 100, 25, 400)
                    ),
                    "padding": str(self._bounded_int(style.get("padding"), 14, 0, 64)),
                    "font_weight": str(
                        self._bounded_int(style.get("font_weight"), 700, 100, 900)
                    ),
                }
        return {
            "border_color": self._valid_color(preset.get("border_color"), "#05070a"),
            "text_font_family": str(preset.get("text_font_family") or "Segoe UI"),
            "text_font_size": font_size,
            "image_fit": fit,
            "image_height_percent": max(35, min(75, image_height)),
            "roles": normalized_roles,
        }

    def _valid_color(self, value: object, fallback: str) -> str:
        color = QColor(str(value or ""))
        return color.name() if color.isValid() else fallback

    @staticmethod
    def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))

    def _complete_field_style(
        self,
        style: dict[str, str] | object,
        background: str,
        text_color: str,
    ) -> dict[str, str]:
        raw = style if isinstance(style, dict) else {}
        alignment = str(raw.get("alignment") or "center")
        if alignment not in {"left", "center", "right"}:
            alignment = "center"
        weight = self._bounded_int(raw.get("font_weight"), 700, 100, 900)
        weight = min((400, 500, 600, 700, 800, 900), key=lambda value: abs(value - weight))
        return {
            "background_color": self._valid_color(raw.get("background_color"), background),
            "text_color": self._valid_color(raw.get("text_color"), text_color),
            "outline_color": self._valid_color(raw.get("outline_color"), "#000000"),
            "outline_width": str(self._bounded_int(raw.get("outline_width"), 0, 0, 8)),
            "border_color": self._valid_color(raw.get("border_color"), "#000000"),
            "border_width": str(self._bounded_int(raw.get("border_width"), 0, 0, 12)),
            "alignment": alignment,
            "font_size": str(self._bounded_int(raw.get("font_size"), 0, 0, 120)),
            "height_weight": str(self._bounded_int(raw.get("height_weight"), 100, 25, 400)),
            "padding": str(self._bounded_int(raw.get("padding"), 14, 0, 64)),
            "font_weight": str(weight),
        }

    def _selected_preset(self) -> dict[str, object] | None:
        data = str(self.preset_combo.currentData() or "")
        if ":" not in data:
            return None
        preset_type, name = data.split(":", 1)
        if preset_type == "builtin":
            preset = BOX_STYLE_PRESETS_BY_NAME.get(name)
        elif preset_type == "custom":
            preset = self.custom_presets.get(name)
        else:
            preset = None
        return self._normalize_preset(preset) if isinstance(preset, dict) else None

    def _apply_selected_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None:
            return
        self.image_height_slider.setValue(int(preset["image_height_percent"]))
        fit_index = self.image_fit_combo.findData(str(preset["image_fit"]))
        if fit_index >= 0:
            self.image_fit_combo.setCurrentIndex(fit_index)
        self.text_font_combo.setCurrentFont(QFont(str(preset["text_font_family"])))
        self.text_font_size_spin.setValue(int(preset["text_font_size"]))
        self.border_color_button.set_color(str(preset["border_color"]))
        role_styles = preset.get("roles", {})
        if isinstance(role_styles, dict):
            for field_id in self.field_roles:
                role = self.field_roles.get(field_id, "category")
                style = role_styles.get(role)
                if not isinstance(style, dict):
                    continue
                current = self.field_styles[field_id]
                self.field_styles[field_id] = self._complete_field_style(
                    style,
                    current["background_color"],
                    current["text_color"],
                )
        self._load_selected_field_style()
        self._update_preview()

    def _save_custom_preset(self) -> None:
        name, accepted = QInputDialog.getText(
            self,
            "Save Custom Preset",
            "Preset name",
        )
        name = name.strip()
        if not accepted or not name:
            return
        self.custom_presets[name] = self._preset_from_current_controls()
        self._save_custom_presets_to_preferences()
        self._populate_preset_combo(f"custom:{name}")

    def _delete_custom_preset(self) -> None:
        data = str(self.preset_combo.currentData() or "")
        if not data.startswith("custom:"):
            QMessageBox.information(
                self,
                "Custom Preset",
                "Select a custom preset to delete.",
            )
            return
        name = data.split(":", 1)[1]
        self.custom_presets.pop(name, None)
        self._save_custom_presets_to_preferences()
        self._populate_preset_combo()

    def _preset_from_current_controls(self) -> dict[str, object]:
        roles: dict[str, dict[str, str]] = {}
        for field_id, role in self.field_roles.items():
            style = self.field_styles[field_id]
            roles[role] = dict(style)
        return {
            "border_color": self.border_color_button.color(),
            "text_font_family": self.text_font_combo.currentFont().family(),
            "text_font_size": self.text_font_size_spin.value(),
            "image_fit": str(self.image_fit_combo.currentData() or "cover"),
            "image_height_percent": int(self.image_height_slider.value()),
            "roles": roles,
        }

    def apply_changes(self) -> None:
        columns = int(self.columns_combo.currentData())
        self.project.preview_max_columns = columns
        setattr(
            self.project,
            f"image_height_percent_{columns}",
            self.image_height_slider.value(),
        )
        self.project.image_fit = str(self.image_fit_combo.currentData())
        self.project.text_font_family = self.text_font_combo.currentFont().family()
        self.project.text_font_size = self.text_font_size_spin.value()
        self.project.item_fixed_duration = float(self.duration_spin.value())
        self.project.card_border_color = self.border_color_button.color()
        self.project.field_styles = {
            field_id: dict(style) for field_id, style in self.field_styles.items()
        }
        preview_fields = self._image_item.display_fields()
        for existing_item in self.project.comparison_items:
            if existing_item is self.item:
                fields = [dict(field) for field in preview_fields]
            else:
                existing_fields = self._fields_with_new_content(
                    existing_item.display_fields()
                )
                values_by_id = {
                    str(field.get("id", "")): str(field.get("value", ""))
                    for field in existing_fields
                }
                fields = []
                for template in preview_fields:
                    field = dict(template)
                    field_id = str(field.get("id", ""))
                    if field_id in values_by_id:
                        field["value"] = values_by_id[field_id]
                    fields.append(field)
            existing_item.set_fields(fields)
            if existing_item is self.item:
                existing_item.image_transforms = {
                    field_id: dict(transform)
                    for field_id, transform in self._image_item.image_transforms.items()
                }
            for new_id, source_id in self._new_field_sources.items():
                if self.field_types.get(new_id) != "image":
                    continue
                source_transform = existing_item.image_transforms.get(source_id)
                if source_transform is not None:
                    existing_item.image_transforms[new_id] = dict(source_transform)
            for layout_columns in range(
                MIN_PREVIEW_COLUMNS_1080P, MAX_PREVIEW_COLUMNS_1080P + 1
            ):
                setattr(existing_item, f"image_height_percent_{layout_columns}", 0)
            existing_item.image_fit = ""
            for key in self.STYLE_KEYS:
                setattr(existing_item, key, "")
        self.project.apply_fixed_item_timing()

    def _edit_image(self, field_id: str) -> None:
        fields = self._image_item.display_fields()
        image_fields = [field for field in fields if field.get("type") == "image"]
        field = next((field for field in image_fields if field.get("id") == field_id), None)
        if field is None:
            return
        columns = int(self.columns_combo.currentData())
        image_height = int(self.project.height * self.image_height_slider.value() / 100)
        if len(image_fields) == len(fields):
            image_height = self.project.height
        frame = QSize(CANVAS_WIDTH // columns, max(1, image_height // len(image_fields)))
        dialog = ImageEditorDialog(
            str(field.get("value", "")), frame,
            str(self.image_fit_combo.currentData() or "cover"),
            self._image_item.image_transforms.get(field_id), self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        field["value"] = dialog.image_path
        self._image_item.set_fields(fields)
        self._image_item.image_transforms[field_id] = dialog.image_transform()
        self._images_changed = True
        self._update_preview()

    def _load_values(self, *_args) -> None:
        columns = int(self.columns_combo.currentData())
        project_height = getattr(self.project, f"image_height_percent_{columns}")
        self.image_height_slider.setValue(project_height)
        self.image_fit_combo.setCurrentIndex(
            max(0, self.image_fit_combo.findData(self.project.image_fit))
        )
        self.text_font_combo.setCurrentFont(QFont(self.project.text_font_family))
        self.border_color_button.set_color(self.project.card_border_color)
        width = CANVAS_WIDTH // columns
        self.box_size_label.setText(f"{width} x {self.project.height} px per box")
        self._update_preview()

    def _image_height_changed(self, value: int) -> None:
        self.image_height_value.setText(f"{value}%")
        self._update_preview()

    def _update_preview(self, *_args) -> None:
        self.box_preview.set_style(
            str(self.image_fit_combo.currentData() or "cover"),
            self.image_height_slider.value(),
            self.border_color_button.color(),
            self.text_font_combo.currentFont().family(),
            self.field_styles,
            self.text_font_size_spin.value(),
            int(self.columns_combo.currentData()),
        )

    def _selected_field_id(self) -> str:
        item = self.field_order_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    def _load_selected_field_style(self) -> None:
        field_id = self._selected_field_id()
        self.box_preview.set_selected_field(field_id)
        field_data = next(
            (
                field
                for field in self._image_item.display_fields()
                if str(field.get("id", "")) == field_id
            ),
            None,
        )
        self._loading_field_content = True
        self.field_label_edit.setText(
            str(field_data.get("label", "")) if field_data else ""
        )
        self.field_value_edit.setText(
            str(field_data.get("value", "")) if field_data else ""
        )
        is_image = bool(field_data and field_data.get("type") == "image")
        self.field_value_edit.setReadOnly(is_image)
        self.field_value_edit.setPlaceholderText(
            "Choose an image" if is_image else "Enter value for this box"
        )
        self.field_browse_button.setVisible(is_image)
        image_style = self.field_styles.get(field_id, {})
        self.image_height_spin.setValue(
            self._bounded_int(image_style.get("height_weight"), 100, 25, 400)
        )
        self.image_height_label.setVisible(is_image)
        self.image_height_spin.setVisible(is_image)
        self.content_group.setEnabled(field_data is not None)
        self._loading_field_content = False
        style = self.field_styles.get(field_id)
        if style is None or is_image:
            self.style_group.setTitle("Selected image")
            self.style_group.setEnabled(False)
            return
        self.style_group.setTitle("Selected text band")
        self.style_group.setEnabled(True)
        self._loading_field_style = True
        self.band_background_button.set_color(style["background_color"])
        self.band_text_button.set_color(style["text_color"])
        self.band_outline_button.set_color(style["outline_color"])
        self.band_border_button.set_color(style["border_color"])
        self.band_outline_width_spin.setValue(int(style["outline_width"]))
        self.band_border_width_spin.setValue(int(style["border_width"]))
        self.band_alignment_combo.setCurrentIndex(
            max(0, self.band_alignment_combo.findData(style["alignment"]))
        )
        self.band_font_weight_combo.setCurrentIndex(
            max(0, self.band_font_weight_combo.findData(int(style["font_weight"])))
        )
        self.band_font_size_spin.setValue(int(style["font_size"]))
        self.band_height_spin.setValue(int(style["height_weight"]))
        self.band_padding_spin.setValue(int(style["padding"]))
        self._loading_field_style = False

    def _selected_field_style_changed(self, *_args) -> None:
        if self._loading_field_style:
            return
        field_id = self._selected_field_id()
        if not field_id:
            return
        self.field_styles[field_id] = {
            "background_color": self.band_background_button.color(),
            "text_color": self.band_text_button.color(),
            "outline_color": self.band_outline_button.color(),
            "outline_width": str(self.band_outline_width_spin.value()),
            "border_color": self.band_border_button.color(),
            "border_width": str(self.band_border_width_spin.value()),
            "alignment": str(self.band_alignment_combo.currentData() or "center"),
            "font_weight": str(self.band_font_weight_combo.currentData() or 700),
            "font_size": str(self.band_font_size_spin.value()),
            "height_weight": str(self.band_height_spin.value()),
            "padding": str(self.band_padding_spin.value()),
        }
        self._update_preview()

    def _selected_field_content_changed(self, *_args) -> None:
        if self._loading_field_content:
            return
        field_id = self._selected_field_id()
        fields = self._image_item.display_fields()
        field = next(
            (field for field in fields if str(field.get("id", "")) == field_id),
            None,
        )
        if field is None:
            return
        field["label"] = self.field_label_edit.text().strip() or str(
            field.get("type", "text")
        ).title()
        if field.get("type") != "image":
            field["value"] = self.field_value_edit.text()
        self._image_item.set_fields(fields)
        current_item = self.field_order_list.currentItem()
        if current_item is not None:
            type_label = "IMAGE" if field.get("type") == "image" else "TEXT"
            current_item.setText(f"{type_label}  ·  {field['label']}")
        self._update_preview()

    def _selected_image_height_changed(self, value: int) -> None:
        if self._loading_field_content:
            return
        field_id = self._selected_field_id()
        if self.field_types.get(field_id) != "image":
            return
        self.field_styles.setdefault(field_id, {})["height_weight"] = str(value)
        self._update_preview()

    def _browse_selected_image(self) -> None:
        field_id = self._selected_field_id()
        if self.field_types.get(field_id) != "image":
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Image",
            str(Path.home()),
            SUPPORTED_IMAGE_FILTER,
        )
        if not path:
            return
        fields = self._image_item.display_fields()
        field = next(
            (field for field in fields if str(field.get("id", "")) == field_id),
            None,
        )
        if field is None:
            return
        field["value"] = path
        self._image_item.set_fields(fields)
        self._images_changed = True
        self._load_selected_field_style()
        self._update_preview()

    def _remove_selected_content(self, field_id: str = "") -> None:
        if self.field_order_list.count() <= 1:
            return
        if field_id:
            self._preview_field_selected(field_id)
        row = self.field_order_list.currentRow()
        field_id = self._selected_field_id()
        fields = [
            field
            for field in self._image_item.display_fields()
            if str(field.get("id", "")) != field_id
        ]
        self._image_item.set_fields(fields)
        self._image_item.image_transforms.pop(field_id, None)
        self.field_styles.pop(field_id, None)
        self.field_roles.pop(field_id, None)
        self.field_types.pop(field_id, None)
        self._new_field_sources.pop(field_id, None)
        removed_item = self.field_order_list.takeItem(row)
        del removed_item
        self.field_order_list.setCurrentRow(
            min(row, self.field_order_list.count() - 1)
        )
        self._update_preview()

    def _add_content_below(self, source_id: str = "") -> None:
        if source_id:
            self._preview_field_selected(source_id)
        source_id = self._selected_field_id()
        fields = self._image_item.display_fields()
        source = next(
            (field for field in fields if str(field.get("id", "")) == source_id),
            None,
        )
        if source is None:
            return
        new_id = f"field_{uuid4().hex[:8]}"
        duplicate = dict(source)
        duplicate["id"] = new_id
        duplicate["label"] = f"{str(source.get('label') or 'Input')} copy"
        source_index = fields.index(source)
        fields.insert(source_index + 1, duplicate)
        source_transform = self._image_item.image_transforms.get(source_id)
        self._image_item.set_fields(fields)
        if source_transform is not None:
            self._image_item.image_transforms[new_id] = dict(source_transform)

        field_type = str(source.get("type", "text"))
        self.field_types[new_id] = field_type
        self._new_field_sources[new_id] = source_id
        if field_type == "image":
            self.field_styles[new_id] = dict(
                self.field_styles.get(source_id, {"height_weight": "100"})
            )
        else:
            self.field_roles[new_id] = self.field_roles.get(source_id, "category")
            self.field_styles[new_id] = dict(
                self.field_styles.get(
                    source_id,
                    self._complete_field_style({}, "#111827", "#ffffff"),
                )
            )

        type_label = "IMAGE" if field_type == "image" else "TEXT"
        list_item = QListWidgetItem(
            f"{type_label}  ·  {duplicate['label']}"
        )
        list_item.setData(Qt.ItemDataRole.UserRole, new_id)
        list_item.setToolTip("Drag to reorder; select to edit this band's style")
        insert_row = self.field_order_list.currentRow() + 1
        self.field_order_list.insertItem(insert_row, list_item)
        self.field_order_list.setCurrentItem(list_item)
        self._field_order_changed()

    def _ordered_field_ids(self) -> list[str]:
        return [
            str(self.field_order_list.item(index).data(Qt.ItemDataRole.UserRole) or "")
            for index in range(self.field_order_list.count())
        ]

    def _ordered_fields(self, fields: list[dict[str, str]]) -> list[dict[str, str]]:
        copied_fields = [dict(field) for field in fields]
        by_id = {str(field.get("id", "")): field for field in copied_fields}
        ordered = [by_id.pop(field_id) for field_id in self._ordered_field_ids() if field_id in by_id]
        ordered.extend(field for field in copied_fields if str(field.get("id", "")) in by_id)
        return ordered

    def _fields_with_new_content(
        self, fields: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        result = [dict(field) for field in fields]
        preview_by_id = {
            str(field.get("id", "")): field
            for field in self._image_item.display_fields()
        }
        for new_id, source_id in self._new_field_sources.items():
            if any(str(field.get("id", "")) == new_id for field in result):
                continue
            source = next(
                (field for field in result if str(field.get("id", "")) == source_id),
                None,
            )
            template = preview_by_id.get(new_id)
            if source is None or template is None:
                continue
            duplicate = dict(source)
            duplicate["id"] = new_id
            duplicate["label"] = str(template.get("label") or source.get("label") or "Input")
            duplicate["type"] = str(template.get("type") or source.get("type") or "text")
            duplicate["role"] = str(template.get("role") or source.get("role") or "")
            result.append(duplicate)
        return result

    def _field_order_changed(self, *_args) -> None:
        self._image_item.set_fields(self._ordered_fields(self._image_item.display_fields()))
        self._update_preview()

    def _preview_field_reorder_requested(
        self, source_id: str, target_id: str, drop_after: bool
    ) -> None:
        source_row = next(
            (
                index
                for index in range(self.field_order_list.count())
                if str(
                    self.field_order_list.item(index).data(Qt.ItemDataRole.UserRole) or ""
                )
                == source_id
            ),
            -1,
        )
        target_row = next(
            (
                index
                for index in range(self.field_order_list.count())
                if str(
                    self.field_order_list.item(index).data(Qt.ItemDataRole.UserRole) or ""
                )
                == target_id
            ),
            -1,
        )
        if source_row < 0 or target_row < 0 or source_row == target_row:
            return
        moved_item = self.field_order_list.takeItem(source_row)
        if source_row < target_row:
            target_row -= 1
        insert_row = target_row + int(drop_after)
        self.field_order_list.insertItem(insert_row, moved_item)
        self.field_order_list.setCurrentItem(moved_item)
        self._field_order_changed()

    def _preview_field_selected(self, field_id: str) -> None:
        for index in range(self.field_order_list.count()):
            item = self.field_order_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == field_id:
                self.field_order_list.setCurrentItem(item)
                break

    def _field_role(self, field_data: dict[str, str], index: int) -> str:
        role = str(field_data.get("role", ""))
        if role in {"name", "category", "rank", "value"}:
            return role
        if field_data.get("type") == "name":
            return "name"
        if field_data.get("type") == "number":
            return "rank"
        return "category" if index < 2 else "value"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project = Project.sample()
        self.project_path: Path | None = None
        self.selected_item_id = self.project.comparison_items[0].id if self.project.comparison_items else ""
        self.current_time = 0.0
        self.playing = False
        self._elapsed = QElapsedTimer()
        self._last_elapsed_ms = 0
        self.preferences = QSettings("DataCompareTools", "DataComparisonVideoMaker")
        self.theme = str(self.preferences.value("theme", "dark")).lower()
        if self.theme not in {"dark", "light"}:
            self.theme = "dark"

        self.setWindowTitle(APP_NAME)
        self.resize(1600, 950)
        self.setMinimumSize(1200, 700)

        self.preview = PreviewWidget()
        self.assets = AssetPanel()
        self.transport = TransportControls()
        self.timeline = TimelineWidget()

        self._build_ui()
        self._build_menu()
        self._build_status_bar()
        self._connect_signals()
        self.set_theme(self.theme)

        self.playback_timer = QTimer(self)
        self.playback_timer.setInterval(16)
        self.playback_timer.timeout.connect(self._playback_tick)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_playback)

        self._refresh_all()

    def _build_ui(self) -> None:
        command_bar = QWidget()
        command_bar.setObjectName("EditorToolbar")
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(14, 9, 14, 9)
        command_layout.setSpacing(8)
        app_title = QLabel("Data Compare")
        app_title.setObjectName("AppTitle")
        self.project_title = QLabel()
        self.project_title.setObjectName("ProjectTitle")
        self.import_data_button = QPushButton("Import Text")
        self.customize_boxes_button = QPushButton("Customize Boxes")
        self.settings_button = QPushButton("Project Settings")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(self.theme.title())
        self.theme_combo.setMinimumWidth(90)
        self.toolbar_export_button = QPushButton("Export")
        self.toolbar_export_button.setObjectName("PrimaryButton")
        command_layout.addWidget(app_title)
        command_layout.addSpacing(8)
        command_layout.addWidget(self.project_title)
        command_layout.addStretch(1)
        command_layout.addWidget(self.import_data_button)
        command_layout.addWidget(self.customize_boxes_button)
        command_layout.addWidget(self.settings_button)
        command_layout.addWidget(QLabel("Theme"))
        command_layout.addWidget(self.theme_combo)
        command_layout.addWidget(self.toolbar_export_button)

        preview_panel = QWidget()
        preview_panel.setObjectName("Panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(8, 8, 8, 0)
        preview_layout.setSpacing(0)
        preview_layout.addWidget(self.preview, 1)
        preview_layout.addWidget(self.transport)

        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.addWidget(self.assets)
        self.top_splitter.addWidget(preview_panel)
        self.top_splitter.setSizes([340, 1260])

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.main_splitter.addWidget(self.top_splitter)
        self.main_splitter.addWidget(self.timeline)
        self.main_splitter.setSizes([660, 290])

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(command_bar)
        central_layout.addWidget(self.main_splitter, 1)
        self.setCentralWidget(central)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        self._add_action(file_menu, "New Project", self.new_project, QKeySequence.StandardKey.New)
        self._add_action(file_menu, "Open Project", self.open_project, QKeySequence.StandardKey.Open)
        self._add_action(file_menu, "Save Project", self.save_project, QKeySequence.StandardKey.Save)
        self._add_action(file_menu, "Save Project As", self.save_project_as, QKeySequence.StandardKey.SaveAs)
        file_menu.addSeparator()
        self._add_action(file_menu, "Import Image", self.import_image)
        self._add_action(file_menu, "Import Text Data", self.add_text, QKeySequence("Ctrl+I"))
        self._add_action(file_menu, "Import Audio", self.import_audio)
        file_menu.addSeparator()
        self._add_action(file_menu, "Exit", self.close, QKeySequence.StandardKey.Quit)

        edit_menu = self.menuBar().addMenu("Edit")
        self._add_action(edit_menu, "Undo", lambda: self._info("Undo will be available after editing history is enabled."), QKeySequence.StandardKey.Undo)
        self._add_action(edit_menu, "Redo", lambda: self._info("Redo will be available after editing history is enabled."), QKeySequence.StandardKey.Redo)
        self._add_action(edit_menu, "Delete", self.delete_selected_item, QKeySequence.StandardKey.Delete)
        self._add_action(edit_menu, "Duplicate", self.duplicate_selected_item, QKeySequence("Ctrl+D"))

        project_menu = self.menuBar().addMenu("Project")
        self._add_action(project_menu, "Project Settings", self.open_project_settings)

        view_menu = self.menuBar().addMenu("View")
        self._add_action(view_menu, "Reset Layout", self._reset_layout)
        self._add_action(view_menu, "Fullscreen", self._toggle_fullscreen, QKeySequence.StandardKey.FullScreen)
        self.show_timeline_action = QAction("Show Timeline", self, checkable=True, checked=True)
        self.show_timeline_action.toggled.connect(self.timeline.setVisible)
        view_menu.addAction(self.show_timeline_action)
        export_menu = self.menuBar().addMenu("Export")
        self._add_action(export_menu, "Export...", self.export_video, QKeySequence("Ctrl+E"))

    def _build_status_bar(self) -> None:
        self.status_label = QLabel()
        self.statusBar().addWidget(self.status_label, 1)

    def _connect_signals(self) -> None:
        self.assets.add_item_requested.connect(self.add_comparison_item)
        self.assets.upload_image_requested.connect(self.import_image)
        self.assets.add_text_requested.connect(self.add_text)
        self.assets.add_audio_requested.connect(self.import_audio)
        self.assets.item_selected.connect(self.select_item)
        self.assets.customize_item_requested.connect(self.open_box_customization)
        self.preview.image_edit_requested.connect(self.open_image_editor)
        self.timeline.item_selected.connect(self.select_item)
        self.timeline.item_timing_changed.connect(self.update_item_timing)
        self.timeline.time_changed.connect(self.set_current_time)
        self.timeline.delete_requested.connect(self.delete_selected_item)
        self.transport.jump_start_requested.connect(lambda: self.set_current_time(0.0))
        self.transport.step_back_requested.connect(lambda: self.set_current_time(self.current_time - 1.0))
        self.transport.play_pause_requested.connect(self.toggle_playback)
        self.transport.stop_requested.connect(self.stop_playback)
        self.transport.step_forward_requested.connect(lambda: self.set_current_time(self.current_time + 1.0))
        self.transport.jump_end_requested.connect(lambda: self.set_current_time(self.project.total_duration()))
        self.transport.columns_changed.connect(self.set_preview_columns)
        self.transport.opening_animation_changed.connect(self.set_opening_animation)
        self.transport.customize_requested.connect(self.open_box_customization)
        self.import_data_button.clicked.connect(self.add_text)
        self.customize_boxes_button.clicked.connect(self.open_box_customization)
        self.settings_button.clicked.connect(self.open_project_settings)
        self.toolbar_export_button.clicked.connect(self.export_video)
        self.theme_combo.currentTextChanged.connect(self.set_theme)

    def _add_action(self, menu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _refresh_all(self) -> None:
        self.project.apply_fixed_item_timing()
        self._normalize_field_schema()
        self._normalize_box_design()
        self.preview.set_project(self.project)
        self.timeline.set_project(self.project)
        self.assets.set_items(self.project.comparison_items, self.selected_item_id)
        self.transport.set_columns(self.project.preview_max_columns)
        self.transport.set_opening_animation(self.project.opening_animation)
        self.select_item(self.selected_item_id, update_asset_panel=False)
        self.set_current_time(self.current_time)
        self._update_status()

    def _normalize_field_schema(self) -> None:
        if not self.project.comparison_items:
            return
        schema = self.project.comparison_items[0].display_fields()
        for item in self.project.comparison_items:
            item.set_fields(self._fields_for_schema(item, schema))

    def _normalize_box_design(self) -> None:
        for item in self.project.comparison_items:
            item.image_fit = ""
            for columns in range(
                MIN_PREVIEW_COLUMNS_1080P, MAX_PREVIEW_COLUMNS_1080P + 1
            ):
                setattr(item, f"image_height_percent_{columns}", 0)
            for key in BoxCustomizationDialog.STYLE_KEYS:
                setattr(item, key, "")

    def _update_status(self) -> None:
        self.project_title.setText(self.project.name)
        self.status_label.setText(
            f"{self.project.name} | {self.project.width} x {self.project.height} | "
            f"{self.project.fps} FPS | {format_timestamp(self.current_time)}"
        )
        self.transport.set_time_text(
            f"{format_timestamp(self.current_time)} / {format_timestamp(self.project.total_duration())}"
        )

    def select_item(self, item_id: str, update_asset_panel: bool = True) -> None:
        self.selected_item_id = item_id
        self.preview.set_selected_item(item_id)
        self.timeline.set_selected_item(item_id)
        if update_asset_panel and item_id:
            self.assets.select_item(item_id)
        self._update_status()

    def set_current_time(self, seconds: float) -> None:
        self.current_time = clamp(seconds, 0.0, self.project.total_duration())
        self.preview.set_current_time(self.current_time)
        self.timeline.set_current_time(self.current_time)
        self._update_status()

    def set_preview_columns(self, columns: int) -> None:
        self.project.preview_max_columns = max(
            MIN_PREVIEW_COLUMNS_1080P,
            min(MAX_PREVIEW_COLUMNS_1080P, int(columns)),
        )
        self.transport.set_columns(self.project.preview_max_columns)
        self.preview.update()
        self._update_status()

    def set_opening_animation(self, animation: str) -> None:
        if animation not in {value for _, value in OPENING_ANIMATION_OPTIONS}:
            animation = "slide_left"
        self.project.opening_animation = animation
        self.transport.set_opening_animation(animation)
        self.preview.update()

    def add_comparison_item(self) -> None:
        schema = (
            self.project.comparison_items[0].display_fields()
            if self.project.comparison_items
            else None
        )
        index = len(self.project.comparison_items) + 1
        item = ComparisonItem(
            name=f"Item {index}",
            rank=f"#{index}",
            category="CATEGORY",
            value="Value",
            start_time=(index - 1) * self.project.item_fixed_duration,
            duration=self.project.item_fixed_duration,
        )
        self.project.comparison_items.append(item)
        if schema:
            for existing_item in self.project.comparison_items:
                if not existing_item.custom_fields:
                    existing_item.set_fields(
                        self._fields_for_schema(existing_item, schema)
                    )
        self.project.apply_fixed_item_timing()
        self.selected_item_id = item.id
        self._refresh_all()

    def add_text(self) -> None:
        dialog = TextImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        imported = dialog.imported_items()
        existing_schema = (
            self.project.comparison_items[0].display_fields()
            if self.project.comparison_items and not dialog.replaces_items()
            else None
        )
        if dialog.replaces_items():
            self.project.comparison_items.clear()
        first_new_id = ""
        for row in imported:
            index = len(self.project.comparison_items) + 1
            item = ComparisonItem(
                name=row["name"],
                rank=row["rank"] or f"#{index}",
                category=row["category"] or "CATEGORY",
                value=row["value"] or "Value",
                image_path=row["image_path"],
                start_time=(index - 1) * self.project.item_fixed_duration,
                duration=self.project.item_fixed_duration,
            )
            self.project.comparison_items.append(item)
            first_new_id = first_new_id or item.id
        schema = existing_schema
        if schema is None and self.project.comparison_items:
            schema = self.project.comparison_items[0].display_fields()
        if schema:
            for existing_item in self.project.comparison_items:
                existing_item.set_fields(self._fields_for_schema(existing_item, schema))
        self.project.apply_fixed_item_timing()
        self.selected_item_id = first_new_id
        self.current_time = 0.0
        self._refresh_all()
        self.statusBar().showMessage(f"Imported {len(imported)} items", 3500)

    def open_box_customization(self, item_id: str = "") -> None:
        item = self.project.item_by_id(item_id or self.selected_item_id)
        if item is None:
            self._warning("Select a comparison item to customize.")
            return
        dialog = BoxCustomizationDialog(self.project, item, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.apply_changes()
        self._refresh_all()
        self.statusBar().showMessage("Updated box content and design", 3500)

    def open_image_editor(self, item_id: str, field_id: str) -> None:
        item = self.project.item_by_id(item_id)
        if item is None:
            return
        fields = item.display_fields()
        images = [field for field in fields if field.get("type") == "image"]
        field = next((field for field in images if field.get("id") == field_id), None)
        if field is None:
            return
        self.pause_playback()
        self.select_item(item_id)
        columns = self.project.preview_max_columns
        percent = (getattr(item, f"image_height_percent_{columns}", 0)
                   or getattr(self.project, f"image_height_percent_{columns}"))
        height = int(self.project.height * percent / 100)
        if len(images) == len(fields):
            height = self.project.height
        frame = QSize(CANVAS_WIDTH // columns, max(1, height // len(images)))
        dialog = ImageEditorDialog(
            str(field.get("value", "")), frame, item.image_fit or self.project.image_fit,
            item.image_transforms.get(field_id), self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        field["value"] = dialog.image_path
        item.set_fields(fields)
        item.image_transforms[field_id] = dialog.image_transform()
        self._refresh_all()
        self.statusBar().showMessage(f"Updated image for {item.name}", 3500)

    def import_image(self) -> None:
        if not self.selected_item_id:
            self._warning("Select a comparison item before assigning an image.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Upload Image",
            str(Path.home()),
            SUPPORTED_IMAGE_FILTER,
        )
        if not path:
            return
        item = self.project.item_by_id(self.selected_item_id)
        if item is None:
            self._warning("The selected item could not be found.")
            return
        item.set_image_path(path)
        self._refresh_all()

    def import_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Audio",
            str(Path.home()),
            SUPPORTED_AUDIO_FILTER,
        )
        if path:
            self.project.audio_paths.append(path)
            self._info(f"Imported audio:\n{path}")
            self._update_status()

    def update_item_properties(self, changes: dict) -> None:
        item = self.project.item_by_id(str(changes.get("id", "")))
        if item is None:
            return
        for key, value in changes.items():
            if key == "id":
                continue
            if key in {"start_time", "duration"}:
                numeric_value = max(0.0, float(value))
                if key == "duration":
                    numeric_value = max(MIN_CLIP_DURATION, numeric_value)
                    self.project.item_fixed_duration = numeric_value
                setattr(item, key, numeric_value)
            elif hasattr(item, key):
                setattr(item, key, str(value))
        if "duration" in changes:
            self.project.apply_fixed_item_timing()
        self._refresh_non_destructive()

    def update_item_fields(self, item_id: str, fields: list) -> None:
        item = self.project.item_by_id(item_id)
        if item is None:
            return
        item.set_fields(fields)
        for existing_item in self.project.comparison_items:
            if existing_item.id == item_id:
                continue
            existing_item.set_fields(self._fields_for_schema(existing_item, fields))
        active_field_ids = {str(field_data.get("id", "")) for field_data in fields}
        self.project.field_styles = {
            field_id: style
            for field_id, style in self.project.field_styles.items()
            if field_id in active_field_ids
        }
        self._refresh_non_destructive()

    def _fields_for_schema(
        self,
        item: ComparisonItem,
        schema: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        existing_fields = item.display_fields()
        used_indexes: set[int] = set()
        result: list[dict[str, str]] = []

        for position, schema_field in enumerate(schema):
            match_index = self._matching_field_index(
                schema_field, position, existing_fields, used_indexes
            )
            value = (
                existing_fields[match_index].get("value", "")
                if match_index is not None
                else ""
            )
            if match_index is not None:
                used_indexes.add(match_index)
            field_data = dict(schema_field)
            field_data["value"] = str(value)
            result.append(field_data)
        return result

    def _matching_field_index(
        self,
        schema_field: dict[str, str],
        position: int,
        existing_fields: list[dict[str, str]],
        used_indexes: set[int],
    ) -> int | None:
        available = [
            (index, field_data)
            for index, field_data in enumerate(existing_fields)
            if index not in used_indexes
        ]
        schema_id = schema_field.get("id", "")
        schema_role = schema_field.get("role", "")
        schema_type = schema_field.get("type", "text")
        schema_label = schema_field.get("label", "")

        checks = [
            lambda field_data: schema_id and field_data.get("id") == schema_id,
            lambda field_data: schema_role and field_data.get("role") == schema_role,
            lambda field_data: (
                not schema_role
                and not field_data.get("role", "")
                and field_data.get("type") == schema_type
                and field_data.get("label") == schema_label
            ),
        ]
        for check in checks:
            for index, field_data in available:
                if check(field_data):
                    return index
        return None

    def update_item_timing(self, item_id: str, start: float, duration: float) -> None:
        item = self.project.item_by_id(item_id)
        if item is None:
            return
        self.project.item_fixed_duration = max(MIN_CLIP_DURATION, float(duration))
        self.project.apply_fixed_item_timing()
        self.preview.update()
        self.timeline.set_project(self.project)
        self._update_status()

    def _refresh_non_destructive(self) -> None:
        self.preview.update()
        self.timeline.set_project(self.project)
        self.timeline.set_selected_item(self.selected_item_id)
        self.assets.set_items(self.project.comparison_items, self.selected_item_id)
        self._update_status()

    def delete_selected_item(self) -> None:
        if not self.selected_item_id:
            return
        item = self.project.item_by_id(self.selected_item_id)
        if item is None:
            return
        response = QMessageBox.question(
            self,
            "Delete Item",
            f"Delete '{item.name}' from the project?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self.project.comparison_items = [
            existing for existing in self.project.comparison_items if existing.id != self.selected_item_id
        ]
        self.selected_item_id = self.project.comparison_items[0].id if self.project.comparison_items else ""
        self._refresh_all()

    def duplicate_selected_item(self) -> None:
        item = self.project.item_by_id(self.selected_item_id)
        if item is None:
            self._warning("Select an item to duplicate.")
            return
        duplicate_data = item.to_dict()
        duplicate_data.pop("id", None)
        duplicate_data["name"] = f"{item.name} Copy"
        duplicate_data["start_time"] = (
            len(self.project.comparison_items) * self.project.item_fixed_duration
        )
        duplicate_data["duration"] = self.project.item_fixed_duration
        duplicate = ComparisonItem.from_dict(duplicate_data)
        self.project.comparison_items.append(duplicate)
        self.project.apply_fixed_item_timing()
        self.selected_item_id = duplicate.id
        self._refresh_all()

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        self.project = Project.sample()
        self.project_path = None
        self.selected_item_id = self.project.comparison_items[0].id if self.project.comparison_items else ""
        self.current_time = 0.0
        self._refresh_all()

    def open_project(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(PROJECTS_DIR),
            f"Data Comparison Projects (*{PROJECT_EXTENSION});;JSON Files (*.json)",
        )
        if not path:
            return
        try:
            self.project = ProjectManager.load(path)
        except ProjectError as exc:
            self._warning(str(exc))
            return
        self.project_path = Path(path)
        self.selected_item_id = self.project.comparison_items[0].id if self.project.comparison_items else ""
        self.current_time = 0.0
        self._refresh_all()

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self._save_to_path(self.project_path)

    def save_project_as(self) -> None:
        default = PROJECTS_DIR / f"{self.project.name.replace(' ', '_').lower()}{PROJECT_EXTENSION}"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project As",
            str(default),
            f"Data Comparison Projects (*{PROJECT_EXTENSION})",
        )
        if path:
            self._save_to_path(Path(path))

    def _save_to_path(self, path: Path) -> None:
        try:
            self.project_path = ProjectManager.save(self.project, path)
        except ProjectError as exc:
            self._warning(str(exc))
            return
        self.statusBar().showMessage(f"Saved {self.project_path}", 3500)

    def open_project_settings(self) -> None:
        dialog = ProjectSettingsDialog(self.project, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply_to(self.project)
            self.set_current_time(min(self.current_time, self.project.total_duration()))
            self._refresh_all()

    def export_video(self) -> None:
        dialog = ExportDialog(
            self.project.name,
            self.project.fps,
            self.project.total_duration(),
            self.project.content_duration(),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = dialog.options()
        self.pause_playback()

        progress_dialog: QProgressDialog | None = None
        if options.format_name != "png":
            progress_dialog = QProgressDialog("Rendering frames...", "Cancel", 0, 1000, self)
            progress_dialog.setWindowTitle("Export")
            progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
            progress_dialog.setMinimumDuration(0)
            progress_dialog.setValue(0)

        def report_progress(current: int, total: int) -> bool:
            if progress_dialog is None:
                return True
            progress_dialog.setValue(round((current / max(1, total)) * 1000))
            progress_dialog.setLabelText(f"Rendering frame {min(current + 1, total):,} of {total:,}")
            QApplication.processEvents()
            return not progress_dialog.wasCanceled()

        try:
            completed = export_preview(
                self.preview, options, self.current_time, report_progress
            )
        except (ExportError, OSError) as exc:
            self._warning(str(exc))
            return
        finally:
            if progress_dialog is not None:
                progress_dialog.close()
        if completed:
            self.statusBar().showMessage(f"Exported {options.path}", 5000)
            self._info(f"Export complete:\n{options.path}")

    def toggle_playback(self) -> None:
        if self.playing:
            self.pause_playback()
            return
        if self.current_time >= self.project.total_duration():
            self.set_current_time(0.0)
        self.playing = True
        self.transport.set_playing(True)
        self._elapsed.restart()
        self._last_elapsed_ms = 0
        self.playback_timer.start()

    def pause_playback(self) -> None:
        self.playing = False
        self.transport.set_playing(False)
        self.playback_timer.stop()

    def stop_playback(self) -> None:
        self.pause_playback()
        self.set_current_time(0.0)

    def _playback_tick(self) -> None:
        if not self.playing:
            return
        elapsed_ms = self._elapsed.elapsed()
        delta = (elapsed_ms - self._last_elapsed_ms) / 1000.0
        self._last_elapsed_ms = elapsed_ms
        next_time = self.current_time + max(0.0, delta)
        if next_time >= self.project.total_duration():
            self.set_current_time(self.project.total_duration())
            self.pause_playback()
            return
        self.set_current_time(next_time)

    def _confirm_discard(self) -> bool:
        response = QMessageBox.question(
            self,
            "Continue?",
            "Unsaved changes are not tracked in this milestone. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        return response == QMessageBox.StandardButton.Yes

    def _reset_layout(self) -> None:
        self.top_splitter.setSizes([340, 1260])
        self.main_splitter.setSizes([660, 290])

    def set_theme(self, theme: str) -> None:
        normalized = theme.lower()
        if normalized not in {"dark", "light"}:
            return
        self.theme = normalized
        self.preferences.setValue("theme", normalized)
        application = QApplication.instance()
        if application is not None:
            application.setStyleSheet(app_style(normalized))
        self.timeline.set_theme(normalized)
        self.update()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _warning(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)

    def _info(self, message: str) -> None:
        QMessageBox.information(self, APP_NAME, message)
