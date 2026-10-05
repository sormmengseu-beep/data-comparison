from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
    QElapsedTimer,
    QMimeData,
    QPoint,
    QRect,
    QSettings,
    QSize,
    QTimer,
    QUrl,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDrag,
    QFont,
    QFontMetrics,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFontComboBox,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
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
    QToolButton,
    QVBoxLayout,
    QWidget,
    QDoubleSpinBox,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.dialogs import ExportDialog, ExportOptions, ImageEditorDialog, TextImportDialog
from app.exporter import ExportError, export_preview
from app.project_manager import ProjectError, ProjectManager
from app.settings import (
    APP_NAME,
    DEFAULT_DURATION,
    DARK_COLORS,
    LIGHT_COLORS,
    MAX_PREVIEW_COLUMNS_1080P,
    MIN_PREVIEW_COLUMNS_1080P,
    MIN_CLIP_DURATION,
    OPENING_ANIMATION_OPTIONS,
    PROJECT_RESOLUTION_PRESETS,
    PROJECT_EXTENSION,
    PROJECTS_DIR,
    SUPPORTED_AUDIO_FILTER,
    SUPPORTED_IMAGE_FILTER,
    app_style,
)
from app.utils.time_utils import clamp, format_timestamp
from app.utils.icons import IconButton
from app.utils.image_utils import ImageCache, draw_image, image_field_frame_size
from app.utils.shape_utils import FILL_OPTIONS, fill_brush, normalized_shape, shape_path
from app.widgets.asset_panel import AssetPanel
from app.widgets.preview_widget import PreviewWidget
from app.widgets.timeline_widget import TimelineWidget
from app.widgets.transport_controls import TransportControls


SHAPE_ITEM_MIME_TYPE = "application/x-data-compare-shape-item"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_AUDIO_SUFFIXES = {".mp3", ".wav", ".aac", ".m4a", ".flac", ".ogg"}


def _first_dropped_image(mime_data: QMimeData) -> str:
    """Return the first supported local image in a drag payload."""
    for url in mime_data.urls() if mime_data.hasUrls() else ():
        path = url.toLocalFile()
        if path and Path(path).suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
            return path
    return ""


class ColorButton(QPushButton):
    color_changed = Signal(str)

    def __init__(
        self,
        color: str,
        parent: QWidget | None = None,
        allow_alpha: bool = False,
    ) -> None:
        super().__init__(parent)
        self._color = color
        self._allow_alpha = allow_alpha
        self.setFixedWidth(124)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        if allow_alpha:
            self.setToolTip(
                "Choose a color and use Alpha in the color picker to make this "
                "gradient stop partly or fully transparent."
            )
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
        if self._allow_alpha:
            dialog = self._create_color_dialog()
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            chosen = dialog.currentColor()
        else:
            chosen = QColorDialog.getColor(QColor(self._color), self, "Choose Color")
        if chosen.isValid():
            color_format = (
                QColor.NameFormat.HexArgb
                if self._allow_alpha and chosen.alpha() < 255
                else QColor.NameFormat.HexRgb
            )
            self.set_color(chosen.name(color_format))

    def _create_color_dialog(self) -> QColorDialog:
        dialog = QColorDialog(QColor(self._color), self)
        dialog.setWindowTitle("Choose Color")
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)

        opacity_row = QWidget(dialog)
        opacity_row.setObjectName("ColorOpacityRow")
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(12, 4, 12, 4)
        opacity_layout.setSpacing(10)
        opacity_layout.addWidget(QLabel("Opacity"))
        opacity_slider = QSlider(Qt.Orientation.Horizontal)
        opacity_slider.setObjectName("ColorOpacitySlider")
        opacity_slider.setRange(0, 100)
        opacity_slider.setValue(round(dialog.currentColor().alpha() * 100 / 255))
        opacity_value = QLabel(f"{opacity_slider.value()}%")
        opacity_value.setObjectName("ColorOpacityValue")
        opacity_value.setMinimumWidth(42)
        opacity_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        opacity_layout.addWidget(opacity_slider, 1)
        opacity_layout.addWidget(opacity_value)

        def set_opacity(value: int) -> None:
            opacity_value.setText(f"{value}%")
            color = dialog.currentColor()
            color.setAlpha(round(255 * value / 100))
            dialog.setCurrentColor(color)

        def sync_opacity(color: QColor) -> None:
            value = round(color.alpha() * 100 / 255)
            opacity_value.setText(f"{value}%")
            opacity_slider.blockSignals(True)
            opacity_slider.setValue(value)
            opacity_slider.blockSignals(False)

        opacity_slider.valueChanged.connect(set_opacity)
        dialog.currentColorChanged.connect(sync_opacity)
        dialog.layout().addWidget(opacity_row)

        buttons = dialog.findChild(QDialogButtonBox)
        if buttons is not None:
            transparent_button = buttons.addButton(
                "Transparent", QDialogButtonBox.ButtonRole.ActionRole
            )

            def choose_transparent() -> None:
                dialog.setCurrentColor(QColor(0, 0, 0, 0))
                dialog.accept()

            transparent_button.clicked.connect(choose_transparent)
        return dialog

    def _update_swatch(self) -> None:
        color = QColor(self._color)
        foreground = "#111827" if color.lightness() > 150 else "#ffffff"
        self.setText(
            "TRANSPARENT"
            if self._allow_alpha and color.alpha() == 0
            else self._color.upper()
        )
        background = (
            f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
            if color.isValid()
            else self._color
        )
        self.setStyleSheet(
            f"QPushButton {{ background: {background}; color: {foreground}; "
            "border: 1px solid rgba(150, 175, 164, 100); font-weight: 700; }"
        )


class ShapeToolButton(QToolButton):
    activated = Signal(str)

    def __init__(
        self,
        item_kind: str,
        label: str,
        symbol: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.item_kind = item_kind
        self._press_position = QPoint()
        self._dragging = False
        if item_kind == "text":
            self.setText(symbol)
        else:
            pixmap = QPixmap(34, 34)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self.palette().color(self.foregroundRole()))
            painter.drawPath(shape_path(QRect(3, 3, 28, 28), item_kind, 5))
            painter.end()
            self.setIcon(QIcon(pixmap))
            self.setIconSize(QSize(32, 32))
        self.setToolTip(f"Drag {label} onto the preview")
        self.setAccessibleName(label)
        self.setFixedSize(54, 46)
        self.setStyleSheet("QToolButton { font-size: 22px; font-weight: 700; }")
        self.clicked.connect(lambda: self.activated.emit(self.item_kind))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not event.buttons() & Qt.MouseButton.LeftButton:
            return super().mouseMoveEvent(event)
        if (
            event.position().toPoint() - self._press_position
        ).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)
        drag = QDrag(self)
        self._dragging = True
        mime_data = QMimeData()
        mime_data.setData(SHAPE_ITEM_MIME_TYPE, self.item_kind.encode("utf-8"))
        drag.setMimeData(mime_data)
        drag.setPixmap(self.grab())
        drag.setHotSpot(event.position().toPoint())
        drag.exec(Qt.DropAction.CopyAction)
        self.setDown(False)

    def mouseReleaseEvent(self, event) -> None:
        if self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ContentOrderDelegate(QStyledItemDelegate):
    BUTTON_SIZE = 28
    BUTTON_GAP = 7

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
        accent = option.palette.highlight().color()
        background = QColor(accent if selected else Qt.GlobalColor.white)
        is_dark = option.palette.text().color().lightness() > 128
        background.setAlpha(38 if selected else (10 if is_dark else 85))
        border = QColor(accent if selected else option.palette.text().color())
        if not selected:
            border.setAlpha(65 if hovered else 30)
        text_color = option.palette.link().color() if selected else option.palette.text().color()
        muted_color = option.palette.placeholderText().color()
        surface = QLinearGradient(row_rect.topLeft(), row_rect.bottomLeft())
        highlight = QColor(background)
        highlight.setAlpha(min(255, background.alpha() + 18))
        surface.setColorAt(0, highlight)
        surface.setColorAt(1, background)
        painter.setBrush(surface)
        painter.setPen(QPen(border, 1))
        painter.drawRoundedRect(row_rect, 8, 8)

        grip_color = accent if selected else muted_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grip_color)
        center_y = row_rect.center().y()
        for x in (row_rect.left() + 13, row_rect.left() + 18):
            for y in (center_y - 5, center_y, center_y + 5):
                painter.drawEllipse(QPoint(x, y), 1, 1)

        add_rect, delete_rect = self.action_rects(option.rect)
        is_parent = bool(index.data(Qt.ItemDataRole.UserRole + 3))
        parent_id = str(index.data(Qt.ItemDataRole.UserRole + 2) or "")
        child_indent = 26 if parent_id else 0
        if parent_id:
            painter.setPen(QPen(accent, 2))
            branch_x = row_rect.left() + 17
            painter.drawLine(branch_x, row_rect.top() + 7, branch_x, row_rect.center().y())
            painter.drawLine(branch_x, row_rect.center().y(), branch_x + 11, row_rect.center().y())
        trailing_space = 158 if is_parent else 72
        text_rect = row_rect.adjusted(31 + child_indent, 0, -trailing_space, 0)
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

        if is_parent:
            badge_rect = QRect(
                add_rect.left() - 84,
                row_rect.center().y() - 10,
                76,
                20,
            )
            badge_fill = QColor(accent)
            badge_fill.setAlpha(22)
            painter.setPen(QPen(accent, 1))
            painter.setBrush(badge_fill)
            painter.drawRoundedRect(badge_rect, 10, 10)
            badge_font = QFont(option.font)
            badge_font.setPixelSize(9)
            badge_font.setBold(True)
            painter.setFont(badge_font)
            painter.setPen(option.palette.link().color())
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "BACKGROUND")

        self._draw_action_button(painter, add_rect, option.palette.link().color(), False)
        can_delete = bool(option.widget and option.widget.count() > 1)
        delete_color = QColor("#e36e87") if can_delete else muted_color
        self._draw_action_button(painter, delete_rect, delete_color, True)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(super().sizeHint(option, index).width(), 62)

    @staticmethod
    def _draw_action_button(
        painter: QPainter, rect: QRect, color: QColor, is_delete: bool
    ) -> None:
        fill = QColor(color)
        fill.setAlpha(12)
        painter.setBrush(fill)
        painter.setPen(QPen(color, 1))
        painter.drawEllipse(rect.adjusted(1, 1, -1, -1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        icon_pen = QPen(color, 1.35)
        icon_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        icon_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(icon_pen)
        center = rect.center()
        if not is_delete:
            painter.drawLine(center.x() - 4, center.y(), center.x() + 4, center.y())
            painter.drawLine(center.x(), center.y() - 4, center.x(), center.y() + 4)
            return
        painter.drawRoundedRect(QRect(center.x() - 3, center.y() - 2, 6, 7), 1, 1)
        painter.drawLine(center.x() - 4, center.y() - 5, center.x() + 4, center.y() - 5)
        painter.drawLine(center.x() - 1, center.y() - 7, center.x() + 1, center.y() - 7)


class ContentOrderList(QListWidget):
    add_requested = Signal(str)
    delete_requested = Signal(str)
    hierarchy_drop_requested = Signal(str, str, bool, str)

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

    def dropEvent(self, event) -> None:
        source_item = self.currentItem()
        if source_item is None:
            super().dropEvent(event)
            return
        source_id = str(source_item.data(Qt.ItemDataRole.UserRole) or "")
        source_type = str(source_item.data(Qt.ItemDataRole.UserRole + 1) or "")
        position = event.position().toPoint()
        target_index = self.indexAt(position)
        if not target_index.isValid():
            self.hierarchy_drop_requested.emit(source_id, "", True, "")
            event.acceptProposedAction()
            return
        target_item = self.item(target_index.row())
        target_id = str(target_item.data(Qt.ItemDataRole.UserRole) or "")
        if not source_id or source_id == target_id:
            event.ignore()
            return
        target_type = str(target_item.data(Qt.ItemDataRole.UserRole + 1) or "")
        target_parent = str(target_item.data(Qt.ItemDataRole.UserRole + 2) or "")
        target_rect = self.visualItemRect(target_item)
        relative_y = position.y() - target_rect.top()
        middle_drop = target_rect.height() * 0.2 <= relative_y <= target_rect.height() * 0.8
        drop_after = relative_y >= target_rect.height() / 2
        parent_id = ""
        if source_type != "image":
            if target_type == "image" and middle_drop:
                parent_id = target_id
                drop_after = True
            elif target_parent:
                parent_id = target_parent
        self.hierarchy_drop_requested.emit(
            source_id, target_id, drop_after, parent_id
        )
        event.acceptProposedAction()


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
        "name": "Hall of Fame Profile",
        "layout_template": "hall_of_fame",
        "border_color": "#061b4f",
        "text_font_family": "Arial",
        "text_font_size": 0,
        "image_fit": "cover",
        "image_height_percent": 75,
        "roles": {
            "name": {
                "background_color": "#082b70",
                "container_color": "#082b70",
                "text_color": "#ffffff",
                "font_size": "46",
                "font_weight": "800",
                "height_weight": "120",
                "padding": "18",
            },
            "category": {
                "background_color": "#ffffff",
                "container_color": "#050505",
                "text_color": "#17417e",
                "font_size": "38",
                "font_weight": "800",
                "height_weight": "110",
                "padding": "12",
                "inset": "26",
                "corner_radius": "28",
            },
            "rank": {
                "background_color": "#050505",
                "container_color": "#050505",
                "text_color": "#ffffff",
                "font_size": "36",
                "font_weight": "500",
                "height_weight": "85",
                "padding": "12",
            },
            "value": {
                "background_color": "#050505",
                "container_color": "#050505",
                "text_color": "#ffffff",
                "font_size": "34",
                "font_weight": "500",
                "height_weight": "85",
                "padding": "12",
            },
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
    layer_order_requested = Signal(str, str)
    item_dropped = Signal(str, QPoint)
    image_file_dropped = Signal(str, QPoint)
    delete_requested = Signal(str)

    def __init__(
        self,
        item: ComparisonItem,
        project_height: int = 1080,
        parent: QWidget | None = None,
        project_width: int = 1920,
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.project_height = max(1, project_height)
        self.project_width = max(1, project_width)
        self.image_fit = "cover"
        self.image_height_percent = 56
        self.border_color = "#05070a"
        self.border_width = 3
        self.text_font_family = "Segoe UI"
        self.text_font_size = 0
        self.columns = MIN_PREVIEW_COLUMNS_1080P
        self.field_styles: dict[str, dict[str, str]] = {}
        self._image_cache = ImageCache()
        self._field_regions: list[tuple[QRect, str, str]] = []
        self._overlay_parent_regions: dict[str, QRect] = {}
        self._press_position: QPoint | None = None
        self._pressed_field_id = ""
        self._pressed_field_type = ""
        self._dragging_field_id = ""
        self._drop_target: tuple[str, bool] | None = None
        self._selected_field_id = ""
        self._overlay_interaction = ""
        self._resize_handle = ""
        self._interaction_rect = QRect()
        self._interaction_parent_rect = QRect()
        self._snap_guides: list[tuple[str, int]] = []
        self.snap_enabled = True
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(
            "Select and freely drag any object. Drag handles to resize; objects snap to edges and centers."
        )
        self.setMinimumSize(220, 280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def dragEnterEvent(self, event) -> None:
        if (
            event.mimeData().hasFormat(SHAPE_ITEM_MIME_TYPE)
            or _first_dropped_image(event.mimeData())
        ):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if (
            (
                event.mimeData().hasFormat(SHAPE_ITEM_MIME_TYPE)
                or _first_dropped_image(event.mimeData())
            )
            and self._canvas_rect().contains(event.position().toPoint())
        ):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event) -> None:
        position = event.position().toPoint()
        if not self._canvas_rect().contains(position):
            event.ignore()
            return
        image_path = _first_dropped_image(event.mimeData())
        if image_path:
            self.image_file_dropped.emit(image_path, position)
            event.acceptProposedAction()
            return
        if not event.mimeData().hasFormat(SHAPE_ITEM_MIME_TYPE):
            return super().dropEvent(event)
        item_kind = bytes(
            event.mimeData().data(SHAPE_ITEM_MIME_TYPE)
        ).decode("utf-8")
        self.item_dropped.emit(item_kind, position)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:
        if (
            event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}
            and self._selected_field_id
        ):
            self.delete_requested.emit(self._selected_field_id)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._overlay_interaction:
            self._reset_drag_state()
            event.accept()
            return
        arrow_deltas = {
            Qt.Key.Key_Left: QPoint(-1, 0),
            Qt.Key.Key_Right: QPoint(1, 0),
            Qt.Key.Key_Up: QPoint(0, -1),
            Qt.Key.Key_Down: QPoint(0, 1),
        }
        if event.key() in arrow_deltas and self._selected_field_id:
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            if self._nudge_selected_overlay(arrow_deltas[event.key()] * step):
                event.accept()
                return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:
        position = event.pos()
        hit = next(
            (
                (field_id, field_type)
                for region, field_id, field_type in reversed(self._field_regions)
                if region.contains(position)
            ),
            None,
        )
        if hit is None:
            super().contextMenuEvent(event)
            return

        field_id, _field_type = hit
        self._selected_field_id = field_id
        self.field_selected.emit(field_id)
        self.setFocus()
        self.update()

        menu = self._layer_context_menu(field_id)
        menu.exec(event.globalPos())
        event.accept()

    def _layer_context_menu(self, field_id: str) -> QMenu:
        menu = QMenu(self)
        sibling_ids = self._layer_sibling_ids(field_id)
        try:
            index = sibling_ids.index(field_id)
        except ValueError:
            index = -1
        actions = (
            ("Bring to Front", "bring_to_front", index >= 0 and index < len(sibling_ids) - 1),
            ("Bring Forward", "bring_forward", index >= 0 and index < len(sibling_ids) - 1),
            ("Send Backward", "send_backward", index > 0),
            ("Send to Back", "send_to_back", index > 0),
        )
        for label, operation, enabled in actions:
            action = menu.addAction(label)
            action.setEnabled(enabled)
            action.triggered.connect(
                lambda _checked=False, op=operation: self.layer_order_requested.emit(
                    field_id, op
                )
            )
        return menu

    def _layer_sibling_ids(self, field_id: str) -> list[str]:
        fields = self.item.display_fields()
        field_types = {
            str(field.get("id", "")): str(field.get("type", "text"))
            for field in fields
        }

        def parent_for(candidate_id: str) -> str:
            if field_types.get(candidate_id) == "image":
                return ""
            parent_id = str(
                self.field_styles.get(candidate_id, {}).get("parent_id", "")
            )
            return parent_id if field_types.get(parent_id) == "image" else ""

        parent_id = parent_for(field_id)
        return [
            candidate_id
            for candidate_id in field_types
            if parent_for(candidate_id) == parent_id
        ]

    def _canvas_rect(self) -> QRect:
        """Fit one correctly proportioned comparison box into the available panel."""
        available = self.rect().adjusted(8, 8, -8, -8)
        if available.isEmpty():
            return QRect()
        source_width = self.project_width / max(1, self.columns)
        scale = min(
            available.width() / source_width,
            available.height() / self.project_height,
        )
        width = max(1, round(source_width * scale))
        height = max(1, round(self.project_height * scale))
        return QRect(0, 0, width, height).translated(
            available.center().x() - width // 2,
            available.center().y() - height // 2,
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            if self._selected_field_id:
                selected_region = next(
                    (
                        region
                        for region, field_id, _field_type in self._field_regions
                        if field_id == self._selected_field_id
                    ),
                    None,
                )
                if selected_region is not None:
                    handle = self._handle_at(position, selected_region)
                    if handle:
                        parent_rect = self._overlay_parent_regions.get(
                            self._selected_field_id
                        )
                        if parent_rect is not None:
                            self._press_position = position
                            self._pressed_field_id = self._selected_field_id
                            self._pressed_field_type = next(
                                (
                                    field_type
                                    for _region, field_id, field_type in self._field_regions
                                    if field_id == self._selected_field_id
                                ),
                                "",
                            )
                            self._overlay_interaction = "resize"
                            self._resize_handle = handle
                            self._interaction_rect = QRect(selected_region)
                            self._interaction_parent_rect = QRect(parent_rect)
                            self.setFocus()
                            self.setCursor(Qt.CursorShape.ClosedHandCursor)
                            event.accept()
                            return
            hit_regions = list(reversed(self._field_regions))
            for region, field_id, field_type in hit_regions:
                parent_rect = self._overlay_parent_regions.get(field_id)
                if region.contains(position):
                    self._press_position = position
                    self._pressed_field_id = field_id
                    self._pressed_field_type = field_type
                    if parent_rect is not None:
                        self._selected_field_id = field_id
                        self.field_selected.emit(field_id)
                        self._overlay_interaction = "move"
                        self._resize_handle = ""
                        self._interaction_rect = QRect(region)
                        self._interaction_parent_rect = QRect(parent_rect)
                        self.setFocus()
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        position = event.position().toPoint()
        if (
            self._overlay_interaction
            and self._press_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self._update_overlay_geometry(position, event.modifiers())
            event.accept()
            return
        if (
            self._press_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (position - self._press_position).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._dragging_field_id = self._pressed_field_id
        if self._dragging_field_id:
            self._drop_target = None
            for region, field_id, _field_type in reversed(self._field_regions):
                if region.contains(position) and field_id != self._dragging_field_id:
                    self._drop_target = (field_id, position.y() >= region.center().y())
                    break
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return
        selected_region = next(
            (
                region
                for region, field_id, _type in self._field_regions
                if field_id == self._selected_field_id
                and field_id in self._overlay_parent_regions
            ),
            None,
        )
        handle = self._handle_at(position, selected_region) if selected_region else ""
        if handle:
            cursor = {
                "n": Qt.CursorShape.SizeVerCursor,
                "s": Qt.CursorShape.SizeVerCursor,
                "e": Qt.CursorShape.SizeHorCursor,
                "w": Qt.CursorShape.SizeHorCursor,
                "nw": Qt.CursorShape.SizeFDiagCursor,
                "se": Qt.CursorShape.SizeFDiagCursor,
                "ne": Qt.CursorShape.SizeBDiagCursor,
                "sw": Qt.CursorShape.SizeBDiagCursor,
            }[handle]
            self.setCursor(cursor)
        elif selected_region and selected_region.contains(position):
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        elif any(region.contains(position) for region, _field_id, _type in self._field_regions):
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._pressed_field_id:
            if self._overlay_interaction:
                self._reset_drag_state()
                event.accept()
                return
            if self._dragging_field_id and self._drop_target is not None:
                target_id, drop_after = self._drop_target
                self.field_reorder_requested.emit(
                    self._dragging_field_id, target_id, drop_after
                )
            elif not self._dragging_field_id:
                self.field_selected.emit(self._pressed_field_id)
            self._reset_drag_state()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            position = event.position().toPoint()
            for region, field_id, field_type in reversed(self._field_regions):
                if field_type == "image" and region.contains(position):
                    self._selected_field_id = field_id
                    self.field_selected.emit(field_id)
                    self.image_clicked.emit(field_id)
                    self.setFocus()
                    self.update()
                    event.accept()
                    return
        super().mouseDoubleClickEvent(event)

    def _reset_drag_state(self) -> None:
        self._press_position = None
        self._pressed_field_id = ""
        self._pressed_field_type = ""
        self._dragging_field_id = ""
        self._drop_target = None
        self._overlay_interaction = ""
        self._resize_handle = ""
        self._interaction_rect = QRect()
        self._interaction_parent_rect = QRect()
        self._snap_guides = []
        self.unsetCursor()
        self.update()

    @staticmethod
    def _resize_handles(rect: QRect) -> dict[str, QRect]:
        size = 7
        half = size // 2
        points = {
            "nw": rect.topLeft(),
            "n": QPoint(rect.center().x(), rect.top()),
            "ne": rect.topRight(),
            "e": QPoint(rect.right(), rect.center().y()),
            "se": rect.bottomRight(),
            "s": QPoint(rect.center().x(), rect.bottom()),
            "sw": rect.bottomLeft(),
            "w": QPoint(rect.left(), rect.center().y()),
        }
        return {
            name: QRect(point.x() - half, point.y() - half, size, size)
            for name, point in points.items()
        }

    def _handle_at(self, position: QPoint, rect: QRect | None) -> str:
        if rect is None or rect.isEmpty():
            return ""
        for name, handle_rect in self._resize_handles(rect).items():
            if handle_rect.adjusted(-5, -5, 5, 5).contains(position):
                return name
        return ""

    def _update_overlay_geometry(
        self,
        position: QPoint,
        modifiers: Qt.KeyboardModifier | Qt.KeyboardModifiers = Qt.KeyboardModifier.NoModifier,
    ) -> None:
        delta = position - self._press_position
        original = self._interaction_rect
        parent = self._interaction_parent_rect
        min_width = min(18, parent.width())
        min_height = min(14, parent.height())
        if self._overlay_interaction == "move":
            x = max(parent.left(), min(original.x() + delta.x(), parent.right() - original.width() + 1))
            y = max(parent.top(), min(original.y() + delta.y(), parent.bottom() - original.height() + 1))
            updated = QRect(x, y, original.width(), original.height())
        else:
            updated = self._resized_overlay_rect(
                original,
                parent,
                self._resize_handle,
                delta,
                min_width,
                min_height,
                bool(modifiers & Qt.KeyboardModifier.ShiftModifier),
                bool(modifiers & Qt.KeyboardModifier.AltModifier),
            )
        updated = self._snap_rect(
            updated,
            parent,
            snap_allowed=not bool(modifiers & Qt.KeyboardModifier.ControlModifier),
        )
        self._store_overlay_rect(
            self._pressed_field_id, updated, self._interaction_parent_rect
        )
        self.update()

    def _nudge_selected_overlay(self, delta: QPoint) -> bool:
        current = next(
            (
                QRect(region)
                for region, field_id, _field_type in self._field_regions
                if field_id == self._selected_field_id
            ),
            QRect(),
        )
        parent = self._overlay_parent_regions.get(self._selected_field_id)
        if current.isEmpty() or parent is None:
            return False
        updated = QRect(current).translated(delta)
        updated.moveLeft(
            max(parent.left(), min(updated.left(), parent.right() - updated.width() + 1))
        )
        updated.moveTop(
            max(parent.top(), min(updated.top(), parent.bottom() - updated.height() + 1))
        )
        self._store_overlay_rect(self._selected_field_id, updated, parent)
        self.update()
        return True

    def _resized_overlay_rect(
        self,
        original: QRect,
        parent: QRect,
        handle: str,
        delta: QPoint,
        min_width: int,
        min_height: int,
        keep_aspect: bool,
        resize_from_center: bool,
    ) -> QRect:
        left = original.left()
        top = original.top()
        right = original.right() + 1
        bottom = original.bottom() + 1
        if "w" in handle:
            left = max(parent.left(), min(left + delta.x(), right - min_width))
        if "e" in handle:
            right = min(parent.right() + 1, max(right + delta.x(), left + min_width))
        if "n" in handle:
            top = max(parent.top(), min(top + delta.y(), bottom - min_height))
        if "s" in handle:
            bottom = min(parent.bottom() + 1, max(bottom + delta.y(), top + min_height))

        if resize_from_center:
            if "w" in handle:
                right = original.right() + 1 - (left - original.left())
            if "e" in handle:
                left = original.left() - (right - (original.right() + 1))
            if "n" in handle:
                bottom = original.bottom() + 1 - (top - original.top())
            if "s" in handle:
                top = original.top() - (bottom - (original.bottom() + 1))

        width = max(min_width, right - left)
        height = max(min_height, bottom - top)
        if keep_aspect and original.height() > 0:
            aspect = original.width() / original.height()
            horizontal = "w" in handle or "e" in handle
            vertical = "n" in handle or "s" in handle
            if horizontal and not vertical:
                height = max(min_height, round(width / aspect))
            elif vertical and not horizontal:
                width = max(min_width, round(height * aspect))
            elif abs(width - original.width()) >= abs(height - original.height()):
                height = max(min_height, round(width / aspect))
            else:
                width = max(min_width, round(height * aspect))
            return self._place_resized_overlay_rect(
                original,
                parent,
                handle,
                min(width, parent.width()),
                min(height, parent.height()),
                resize_from_center,
            )

        return self._bound_overlay_rect(
            QRect(left, top, width, height),
            parent,
        )

    @staticmethod
    def _place_resized_overlay_rect(
        original: QRect,
        parent: QRect,
        handle: str,
        width: int,
        height: int,
        resize_from_center: bool,
    ) -> QRect:
        if resize_from_center:
            center = original.center()
            rect = QRect(0, 0, width, height)
            rect.moveCenter(center)
            return BoxStylePreview._bound_overlay_rect(rect, parent)

        if "w" in handle:
            left = original.right() + 1 - width
        elif "e" in handle:
            left = original.left()
        else:
            left = original.center().x() - width // 2

        if "n" in handle:
            top = original.bottom() + 1 - height
        elif "s" in handle:
            top = original.top()
        else:
            top = original.center().y() - height // 2
        return BoxStylePreview._bound_overlay_rect(QRect(left, top, width, height), parent)

    @staticmethod
    def _bound_overlay_rect(rect: QRect, parent: QRect) -> QRect:
        bounded = QRect(rect)
        if parent.isEmpty():
            return bounded
        if bounded.width() > parent.width():
            bounded.setWidth(parent.width())
        if bounded.height() > parent.height():
            bounded.setHeight(parent.height())
        bounded.moveLeft(
            max(parent.left(), min(bounded.left(), parent.right() - bounded.width() + 1))
        )
        bounded.moveTop(
            max(parent.top(), min(bounded.top(), parent.bottom() - bounded.height() + 1))
        )
        return bounded

    def _snap_rect(self, rect: QRect, parent: QRect, snap_allowed: bool = True) -> QRect:
        self._snap_guides = []
        if not self.snap_enabled or not snap_allowed:
            return rect
        threshold = 6
        x_targets = {parent.left(), parent.center().x(), parent.right() + 1}
        y_targets = {parent.top(), parent.center().y(), parent.bottom() + 1}
        for region, field_id, _field_type in self._field_regions:
            if field_id == self._pressed_field_id:
                continue
            x_targets.update((region.left(), region.center().x(), region.right() + 1))
            y_targets.update((region.top(), region.center().y(), region.bottom() + 1))

        result = QRect(rect)
        if self._overlay_interaction == "move":
            x_points = (result.left(), result.center().x(), result.right() + 1)
            y_points = (result.top(), result.center().y(), result.bottom() + 1)
            x_match = self._nearest_snap(x_points, x_targets, threshold)
            y_match = self._nearest_snap(y_points, y_targets, threshold)
            if x_match:
                result.translate(x_match[1] - x_match[0], 0)
                self._snap_guides.append(("v", x_match[1]))
            if y_match:
                result.translate(0, y_match[1] - y_match[0])
                self._snap_guides.append(("h", y_match[1]))
        else:
            handle = self._resize_handle
            if "w" in handle or "e" in handle:
                edge = result.left() if "w" in handle else result.right() + 1
                match = self._nearest_snap((edge,), x_targets, threshold)
                if match:
                    if "w" in handle:
                        result.setLeft(match[1])
                    else:
                        result.setRight(match[1] - 1)
                    self._snap_guides.append(("v", match[1]))
            if "n" in handle or "s" in handle:
                edge = result.top() if "n" in handle else result.bottom() + 1
                match = self._nearest_snap((edge,), y_targets, threshold)
                if match:
                    if "n" in handle:
                        result.setTop(match[1])
                    else:
                        result.setBottom(match[1] - 1)
                    self._snap_guides.append(("h", match[1]))
        result.moveLeft(max(parent.left(), min(result.left(), parent.right() - result.width() + 1)))
        result.moveTop(max(parent.top(), min(result.top(), parent.bottom() - result.height() + 1)))
        return result

    @staticmethod
    def _nearest_snap(
        points: tuple[int, ...], targets: set[int], threshold: int
    ) -> tuple[int, int] | None:
        matches = [
            (point, target)
            for point in points
            for target in targets
            if abs(point - target) <= threshold
        ]
        return min(matches, key=lambda pair: abs(pair[0] - pair[1])) if matches else None

    def _store_overlay_rect(
        self, field_id: str, rect: QRect, parent_rect: QRect
    ) -> None:
        if parent_rect.width() <= 0 or parent_rect.height() <= 0:
            return
        width = max(20, min(1000, round(rect.width() * 1000 / parent_rect.width())))
        height = max(20, min(1000, round(rect.height() * 1000 / parent_rect.height())))
        x = max(0, min(1000 - width, round((rect.x() - parent_rect.x()) * 1000 / parent_rect.width())))
        y = max(0, min(1000 - height, round((rect.y() - parent_rect.y()) * 1000 / parent_rect.height())))
        style = self.field_styles.setdefault(field_id, {})
        style.update(
            {
                "overlay_x": str(x),
                "overlay_y": str(y),
                "overlay_width": str(width),
                "overlay_height": str(height),
            }
        )

    def set_style(
        self,
        image_fit: str,
        image_height_percent: int,
        border_color: str,
        text_font_family: str,
        field_styles: dict[str, dict[str, str]],
        text_font_size: int = 0,
        columns: int = MIN_PREVIEW_COLUMNS_1080P,
        snap_enabled: bool = True,
        border_width: int = 3,
    ) -> None:
        self.image_fit = image_fit
        self.image_height_percent = image_height_percent
        self.border_color = border_color
        self.border_width = max(0, min(40, int(border_width)))
        self.text_font_family = text_font_family
        self.field_styles = field_styles
        self.text_font_size = text_font_size
        self.columns = columns
        self.snap_enabled = snap_enabled
        self.update()

    def set_selected_field(self, field_id: str) -> None:
        self._selected_field_id = field_id
        self.update()

    def fields_in_visual_order(self) -> list[dict[str, str]]:
        # Use the rendered geometry so free moves and image overlays share the import order.
        snapshot = QPixmap(self.size())
        snapshot.fill(Qt.GlobalColor.transparent)
        self.render(snapshot)
        fields_by_id = {str(field["id"]): field for field in self.item.display_fields()}
        regions = sorted(self._field_regions, key=lambda region: (region[0].top(), region[0].left()))
        return [dict(fields_by_id[field_id]) for _rect, field_id, _type in regions]

    def paintEvent(self, event) -> None:
        self._field_regions = []
        self._overlay_parent_regions = {}
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        canvas = self._canvas_rect()
        if canvas.isEmpty():
            painter.end()
            return
        painter.fillRect(canvas, QColor("#0b0d10"))
        card = canvas.adjusted(8, 8, -8, -8)
        fields = self.item.display_fields()
        fields_by_id = {str(field.get("id", "")): field for field in fields}
        children_by_parent: dict[str, list[dict[str, str]]] = {}
        root_fields: list[dict[str, str]] = []
        for field in fields:
            field_id = str(field.get("id", ""))
            parent_id = str(self.field_styles.get(field_id, {}).get("parent_id", ""))
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
        content_fields = [
            field for field in root_fields if field.get("type") != "image"
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
            fallback_row = QRect(card.x(), row_y, card.width(), row_height)
            field_style = self.field_styles.get(field_id, {})
            row = self._overlay_rect(card, fallback_row, field_style)
            self._field_regions.append((row, field_id, field_type))
            self._overlay_parent_regions[field_id] = QRect(card)
            if field_type == "image":
                painter.save()
                painter.setClipPath(
                    shape_path(
                        row,
                        field_style.get("shape", "rectangle"),
                        self._style_int(field_style, "corner_radius", 0, 0, 64),
                    ),
                    Qt.ClipOperation.IntersectClip,
                )
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
                child_fields = children_by_parent.get(field_id, [])
                self._draw_image_gradient(
                    painter,
                    row,
                    self.field_styles.get(field_id, {}),
                )
                painter.restore()
                if child_fields:
                    child_weights = [
                        self._style_int(
                            self.field_styles.get(str(child.get("id", "")), {}),
                            "height_weight",
                            100,
                            25,
                            400,
                        )
                        for child in child_fields
                    ]
                    child_y = row.y()
                    child_pixels = row.height()
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
                            row.x(), child_y, row.width(), child_height
                        )
                        child_id = str(child.get("id", ""))
                        child_rect = self._overlay_rect(
                            row,
                            child_rect,
                            self.field_styles.get(child_id, {}),
                        )
                        self._field_regions.append(
                            (child_rect, child_id, str(child.get("type", "text")))
                        )
                        self._overlay_parent_regions[child_id] = QRect(row)
                        self._draw_overlay_text_band(
                            painter, card, child_rect, child, child_index
                        )
                        child_y += child_height
                        child_pixels -= child_height
                        child_weight_total -= child_weight
                row_y += row_height
                remaining_image_pixels -= row_height
                remaining_image_weight -= image_weight
                image_index += 1
                continue

            role = self._preview_field_role(field_data, content_index)
            style = self.field_styles.get(str(field_data.get("id", "")), {})
            scale = card.width() / (self.project_width / self.columns)
            background_color = QColor(style.get("background_color", "#111827"))
            inset = max(0, round(self._style_int(style, "inset", 0, 0, 96) * scale))
            band_rect = row.adjusted(inset, 0, -inset, 0)
            corner_radius = max(
                0,
                round(self._style_int(style, "corner_radius", 0, 0, 64) * scale),
            )
            painter.setPen(Qt.PenStyle.NoPen)
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
            font_size = 15 if role in {"name", "rank"} else 13
            padding = self._style_int(style, "padding", 14, 0, 64)
            preview_padding = max(2, round(padding * scale))
            target = band_rect.adjusted(preview_padding, 2, -preview_padding, -2)
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
                border_rect = band_rect.adjusted(inset, inset, -inset, -inset)
                painter.drawPath(
                    shape_path(
                        border_rect,
                        style.get("shape", "rectangle"),
                        corner_radius,
                    )
                )
            row_y += row_height
            remaining_text_pixels -= row_height
            remaining_text_weight -= weight
            content_index += 1

        painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.border_width > 0:
            scale = card.height() / max(1, self.project_height)
            border_width = max(1, round(self.border_width * scale))
            painter.setPen(QPen(QColor(self.border_color), border_width))
            inset = max(1, (border_width + 1) // 2)
            painter.drawRect(card.adjusted(inset, inset, -inset, -inset))
        if self._selected_field_id and not self._dragging_field_id:
            for region, field_id, _field_type in self._field_regions:
                if field_id == self._selected_field_id:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(QColor("#2563eb"), 1))
                    painter.drawRect(region.adjusted(0, 0, -1, -1))
                    if field_id in self._overlay_parent_regions:
                        painter.setBrush(QColor("#ffffff"))
                        painter.setPen(QPen(QColor("#2563eb"), 1))
                        for handle_rect in self._resize_handles(region).values():
                            painter.drawRect(handle_rect)
                    else:
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
        if self._snap_guides:
            painter.setPen(QPen(QColor("#f43f5e"), 1, Qt.PenStyle.DashLine))
            for orientation, coordinate in self._snap_guides:
                if orientation == "v":
                    painter.drawLine(coordinate, card.top(), coordinate, card.bottom())
                else:
                    painter.drawLine(card.left(), coordinate, card.right(), coordinate)
        painter.end()

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
        width = max(1, round(parent.width() * width_value / 1000))
        height = max(1, round(parent.height() * height_value / 1000))
        x = parent.x() + round(parent.width() * x_value / 1000)
        y = parent.y() + round(parent.height() * y_value / 1000)
        return QRect(x, y, width, height)

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

    def _draw_overlay_text_band(
        self,
        painter: QPainter,
        card: QRect,
        row: QRect,
        field_data: dict[str, str],
        content_index: int,
    ) -> None:
        style = self.field_styles.get(str(field_data.get("id", "")), {})
        scale = card.width() / (self.project_width / self.columns)
        inset = max(0, round(self._style_int(style, "inset", 0, 0, 96) * scale))
        band_rect = row.adjusted(inset, 0, -inset, 0)
        corner_radius = max(
            0, round(self._style_int(style, "corner_radius", 0, 0, 64) * scale)
        )
        background = QColor(style.get("background_color", "#111827"))
        if (
            inset
            or corner_radius
            or style.get("shape", "rectangle") != "rectangle"
            or style.get("fill_mode", "solid") != "solid"
        ):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(
                fill_brush(
                    band_rect,
                    background.name(),
                    style.get("gradient_color_2", background.name()),
                    style.get("fill_mode", "solid"),
                )
            )
            painter.drawPath(
                shape_path(band_rect, style.get("shape", "rectangle"), corner_radius)
            )
        role = self._preview_field_role(field_data, content_index)
        font_size = 15 if role in {"name", "rank"} else 13
        custom_size = self._style_int(style, "font_size", 0, 0, 120)
        if custom_size:
            font_size = max(1, round(custom_size * scale))
        elif self.text_font_size:
            source_size = self.text_font_size if role in {"name", "rank"} else max(
                1, int(self.text_font_size * 0.88)
            )
            font_size = max(1, round(source_size * scale))
        weight_value = self._style_int(style, "font_weight", 700, 100, 900)
        weight_value = min(
            (100, 200, 300, 400, 500, 600, 700, 800, 900),
            key=lambda value: abs(value - weight_value),
        )
        painter.setFont(QFont(self.text_font_family, font_size, QFont.Weight(weight_value)))
        padding = max(
            2, round(self._style_int(style, "padding", 14, 0, 64) * scale)
        )
        target = band_rect.adjusted(padding, 2, -padding, -2)
        horizontal = {
            "left": Qt.AlignmentFlag.AlignLeft,
            "right": Qt.AlignmentFlag.AlignRight,
        }.get(style.get("alignment", "center"), Qt.AlignmentFlag.AlignHCenter)
        flags = horizontal | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap
        text = str(field_data.get("value", ""))
        outline_width = max(
            0, round(self._style_int(style, "outline_width", 0, 0, 8) * scale)
        )
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
        painter.drawText(target, flags, text)
        border_width = max(
            0, round(self._style_int(style, "border_width", 0, 0, 12) * scale)
        )
        if border_width:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(
                QPen(QColor(style.get("border_color", "#000000")), border_width)
            )
            border_rect = band_rect.adjusted(1, 1, -2, -2)
            painter.drawPath(
                shape_path(
                    border_rect,
                    style.get("shape", "rectangle"),
                    corner_radius,
                )
            )

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


class CanvasBackgroundDialog(QDialog):
    def __init__(self, project: Project, current_time: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Canvas Background")
        self.setMinimumWidth(560)
        self.resize(640, 500)
        self._project = deepcopy(project)

        layout = QVBoxLayout(self)
        self.preview = PreviewWidget()
        self.preview.set_project(self._project)
        self.preview.set_current_time(current_time)
        self.preview.setToolTip("")
        layout.addWidget(self.preview, 1)

        form = QFormLayout()
        self.color_button = ColorButton(project.canvas_background_color)
        form.addRow("Color", self.color_button)
        image_row = QHBoxLayout()
        self.image_edit = QLineEdit(project.canvas_background_image)
        self.image_edit.setReadOnly(True)
        self.image_edit.setPlaceholderText("No image")
        self.choose_button = IconButton("image", "Upload background image")
        self.choose_button.setFixedSize(40, 40)
        self.remove_button = IconButton("trash", "Remove background image")
        self.remove_button.setFixedSize(40, 40)
        image_row.addWidget(self.image_edit, 1)
        image_row.addWidget(self.choose_button)
        image_row.addWidget(self.remove_button)
        form.addRow("Image", image_row)
        self.fit_combo = QComboBox()
        for label, value in (
            ("Cover - crop to fill", "cover"),
            ("Contain - show full image", "contain"),
            ("Stretch - fill frame", "stretch"),
        ):
            self.fit_combo.addItem(label, value)
        self.fit_combo.setCurrentIndex(max(0, self.fit_combo.findData(project.canvas_background_fit)))
        form.addRow("Image fit", self.fit_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.color_button.color_changed.connect(self._update_preview)
        self.image_edit.textChanged.connect(self._update_preview)
        self.fit_combo.currentIndexChanged.connect(self._update_preview)
        self.choose_button.clicked.connect(self._choose_image)
        self.remove_button.clicked.connect(lambda: self.image_edit.clear())
        self._update_preview()

    def _choose_image(self) -> None:
        directory = str(Path(self.image_edit.text()).parent) if self.image_edit.text() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload Background Image", directory, SUPPORTED_IMAGE_FILTER
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "Background Image", "The selected image could not be opened.")
            return
        self.image_edit.setText(str(Path(path).resolve()))

    def _update_preview(self, *_args) -> None:
        self.apply_to(self._project)
        self.remove_button.setEnabled(bool(self.image_edit.text()))
        self.fit_combo.setEnabled(bool(self.image_edit.text()))
        self.preview.set_project(self._project)

    def apply_to(self, project: Project) -> None:
        project.canvas_background_color = self.color_button.color()
        project.canvas_background_image = self.image_edit.text()
        project.canvas_background_fit = str(self.fit_combo.currentData())


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
        self.resolution_combo = QComboBox()
        for label, width, height in PROJECT_RESOLUTION_PRESETS:
            self.resolution_combo.addItem(
                f"{label} - {width} x {height}", (width, height)
            )
        self.resolution_combo.addItem("Custom", None)
        resolution_index = next(
            (
                index
                for index in range(self.resolution_combo.count())
                if self.resolution_combo.itemData(index)
                == (project.width, project.height)
            ),
            -1,
        )
        self.resolution_combo.setCurrentIndex(
            resolution_index
            if resolution_index >= 0
            else self.resolution_combo.count() - 1
        )
        resolution_size = QWidget()
        resolution_size_layout = QHBoxLayout(resolution_size)
        resolution_size_layout.setContentsMargins(0, 0, 0, 0)
        resolution_size_layout.setSpacing(8)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(320, 7680)
        self.width_spin.setValue(project.width)
        self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(240, 4320)
        self.height_spin.setValue(project.height)
        self.height_spin.setSuffix(" px")
        resolution_size_layout.addWidget(self.width_spin)
        resolution_size_layout.addWidget(QLabel("×"))
        resolution_size_layout.addWidget(self.height_spin)
        resolution_size_layout.addStretch(1)
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
        form.addRow("Resolution", self.resolution_combo)
        form.addRow("Frame Size", resolution_size)
        form.addRow("FPS", self.fps_combo)
        form.addRow("Preview Columns", self.preview_columns_spin)
        form.addRow("Opening Animation", self.opening_animation_combo)
        form.addRow("Box Duration", self.item_duration_spin)
        self.animation_length_label = QLabel()
        form.addRow("Animation Length", self.animation_length_label)
        self.item_duration_spin.valueChanged.connect(self._update_animation_length)
        self.resolution_combo.currentIndexChanged.connect(self._resolution_changed)
        self._resolution_changed()
        self._update_animation_length(self.item_duration_spin.value())
        tabs.addTab(general_page, "General")

        design_page = QWidget()
        design_form = QFormLayout(design_page)
        self.canvas_color_button = ColorButton(project.canvas_background_color)
        self.border_color_button = ColorButton(project.card_border_color)
        self.border_width_spin = QSpinBox()
        self.border_width_spin.setRange(0, 40)
        self.border_width_spin.setSuffix(" px")
        self.border_width_spin.setSpecialValueText("None")
        self.border_width_spin.setValue(project.card_border_width)
        self.text_font_combo = QFontComboBox()
        self.text_font_combo.setCurrentFont(QFont(project.text_font_family))
        design_form.addRow("Canvas Background", self.canvas_color_button)
        border_row = QWidget()
        border_layout = QHBoxLayout(border_row)
        border_layout.setContentsMargins(0, 0, 0, 0)
        border_layout.setSpacing(8)
        border_layout.addWidget(self.border_color_button)
        border_layout.addWidget(self.border_width_spin)
        border_layout.addStretch(1)
        design_form.addRow("Box Border", border_row)
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
        project.width = self.width_spin.value()
        project.height = self.height_spin.value()
        project.fps = int(self.fps_combo.currentText())
        project.preview_max_columns = int(self.preview_columns_spin.value())
        project.opening_animation = str(self.opening_animation_combo.currentData())
        project.item_fixed_duration = float(self.item_duration_spin.value())
        project.canvas_background_color = self.canvas_color_button.color()
        project.card_border_color = self.border_color_button.color()
        project.card_border_width = self.border_width_spin.value()
        project.text_font_family = self.text_font_combo.currentFont().family()
        for key, (background_button, text_button) in self.band_color_buttons.items():
            setattr(project, f"{key}_background_color", background_button.color())
            setattr(project, f"{key}_text_color", text_button.color())
        project.field_styles.clear()
        project.apply_fixed_item_timing()

    def _resolution_changed(self, *_args) -> None:
        preset = self.resolution_combo.currentData()
        is_custom = preset is None
        if preset is not None:
            width, height = preset
            self.width_spin.setValue(int(width))
            self.height_spin.setValue(int(height))
        self.width_spin.setEnabled(is_custom)
        self.height_spin.setEnabled(is_custom)

    def _update_animation_length(self, box_duration: float) -> None:
        duration = self._item_count * box_duration if self._item_count else 0.0
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
        self._all_box_image_updates: dict[str, tuple[str, dict[str, float | str]]] = {}
        self._images_changed = False
        self.preferences = QSettings("DataCompareTools", "DataComparisonVideoMaker")
        self.custom_presets = self._load_custom_presets()
        self.setObjectName("BoxCustomizationDialog")
        self.setWindowTitle("Customize All Boxes")
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self.setMinimumSize(980, 650)
        self.resize(1280, 820)

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

        layout_group = QGroupBox()
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
        self.apply_preset_button = IconButton("check", "Apply selected preset", preset_row)
        self.save_preset_button = IconButton("save", "Save current design as a custom preset", preset_row)
        self.delete_preset_button = IconButton("trash", "Delete selected custom preset", preset_row)
        for button in (self.apply_preset_button, self.save_preset_button, self.delete_preset_button):
            button.setObjectName("PresetAction")
            button.setFixedSize(40, 40)
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(self.apply_preset_button)
        preset_layout.addWidget(self.save_preset_button)
        preset_layout.addWidget(self.delete_preset_button)
        form.addRow("Preset", preset_row)
        self._populate_preset_combo()

        # Presets retain their image-height setting without exposing a slider.
        self.image_height_slider = QSlider(Qt.Orientation.Horizontal, self)
        self.image_height_slider.setRange(35, 75)
        self.image_height_slider.setSingleStep(1)
        self.image_height_slider.hide()

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

        self.border_color_button = ColorButton(project.card_border_color)
        self.border_width_spin = QSpinBox()
        self.border_width_spin.setRange(0, 40)
        self.border_width_spin.setSuffix(" px")
        self.border_width_spin.setSpecialValueText("None")
        self.border_width_spin.setValue(project.card_border_width)
        self.border_width_spin.setToolTip("Outer border thickness at 1080p; choose None to hide it.")
        border_row = QWidget()
        border_layout = QHBoxLayout(border_row)
        border_layout.setContentsMargins(0, 0, 0, 0)
        border_layout.setSpacing(8)
        border_layout.addWidget(self.border_color_button)
        border_layout.addWidget(self.border_width_spin)
        border_layout.addStretch(1)
        form.addRow("Box border", border_row)
        self.snap_objects_check = QCheckBox("Snap to edges, centers, and objects")
        self.snap_objects_check.setChecked(True)
        self.snap_objects_check.setToolTip(
            "Shows smart guides and aligns objects while moving or resizing."
        )
        snap_row = QWidget()
        snap_row.setObjectName("DesignerCompactOption")
        snap_row.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
        )
        snap_layout = QHBoxLayout(snap_row)
        snap_layout.setContentsMargins(10, 0, 10, 0)
        snap_layout.setSpacing(6)
        snap_layout.addWidget(self.snap_objects_check)
        form.addRow("Free move", snap_row)
        controls_layout.addWidget(layout_group)

        palette_group = QGroupBox()
        self.shape_palette_group = palette_group
        palette_group.setObjectName("DesignerSection")
        palette_layout = QVBoxLayout(palette_group)
        palette_layout.setContentsMargins(10, 8, 10, 10)
        palette_layout.setSpacing(8)

        shapes_label = QLabel("SHAPES  •  CLICK OR DRAG")
        shapes_label.setObjectName("DesignerPaletteLabel")

        shape_scroll = QScrollArea()
        shape_scroll.setObjectName("DesignerShapeScroll")
        shape_scroll.setWidgetResizable(True)
        shape_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        shape_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        shape_scroll.setFixedHeight(252)
        shape_container = QWidget()
        shape_container.setObjectName("DesignerShapeGrid")
        shape_grid = QGridLayout(shape_container)
        shape_grid.setContentsMargins(5, 5, 5, 5)
        shape_grid.setHorizontalSpacing(7)
        shape_grid.setVerticalSpacing(7)
        palette_items = (
            ("rectangle", "Rectangle", "▰"),
            ("rounded", "Rounded rectangle", "▢"),
            ("pill", "Pill", "▬"),
            ("circle", "Circle", "●"),
            ("ellipse", "Ellipse", "⬭"),
            ("triangle", "Triangle", "▲"),
            ("triangle_down", "Down triangle", "▼"),
            ("diamond", "Diamond", "◆"),
            ("pentagon", "Pentagon", "⬟"),
            ("hexagon", "Hexagon", "⬢"),
            ("octagon", "Octagon", "8"),
            ("star", "Star", "★"),
            ("burst", "Burst", "✹"),
            ("chevron", "Chevron", "❯"),
            ("arrow_left", "Left arrow", "←"),
            ("arrow_right", "Right arrow", "→"),
            ("parallelogram", "Parallelogram", "▱"),
            ("trapezoid", "Trapezoid", "⏢"),
            ("cross", "Cross", "✚"),
            ("heart", "Heart", "♥"),
        )
        self.shape_tool_buttons: dict[str, ShapeToolButton] = {}
        self.additional_shape_tool_buttons: dict[str, ShapeToolButton] = {}
        original_shape_kinds = {
            "rectangle", "rounded", "pill", "circle", "ellipse", "triangle",
            "diamond", "hexagon", "star",
        }
        for index, (item_kind, label, symbol) in enumerate(palette_items):
            button = ShapeToolButton(item_kind, label, symbol, shape_container)
            button.activated.connect(self._palette_item_activated)
            target = (
                self.shape_tool_buttons
                if item_kind in original_shape_kinds
                else self.additional_shape_tool_buttons
            )
            target[item_kind] = button
            shape_grid.addWidget(button, index // 5, index % 5)
        self.all_shape_tool_buttons = {
            **self.shape_tool_buttons,
            **self.additional_shape_tool_buttons,
        }
        shape_grid.setColumnStretch(5, 1)
        shape_scroll.setWidget(shape_container)
        self.shape_palette_scroll = shape_scroll

        palette_body = QHBoxLayout()
        palette_body.setSpacing(10)
        shape_panel = QWidget()
        shape_panel_layout = QVBoxLayout(shape_panel)
        shape_panel_layout.setContentsMargins(0, 0, 0, 0)
        shape_panel_layout.setSpacing(6)
        shape_panel_layout.addWidget(shapes_label)
        shape_panel_layout.addWidget(shape_scroll)
        palette_body.addWidget(shape_panel, 3)

        records_panel = QWidget()
        records_layout = QVBoxLayout(records_panel)
        records_layout.setContentsMargins(0, 0, 0, 0)
        records_layout.setSpacing(6)
        records_label = QLabel("RECORDS  |  SELECT TO EDIT")
        records_label.setObjectName("DesignerPaletteLabel")
        records_layout.addWidget(records_label)
        self.field_order_list = ContentOrderList(self)
        self.field_order_list.setObjectName("DesignerOrderList")
        self.field_order_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.field_order_list.setItemDelegate(ContentOrderDelegate(self.field_order_list))
        self.field_order_list.setDragEnabled(True)
        self.field_order_list.setAcceptDrops(True)
        self.field_order_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.field_order_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.field_order_list.setFixedHeight(252)
        records_layout.addWidget(self.field_order_list)
        palette_body.addWidget(records_panel, 2)
        palette_layout.addLayout(palette_body)
        controls_layout.addWidget(palette_group)

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
                self.field_styles[field_id] = self._complete_image_style(saved_style)
            else:
                role = self._field_role(field_data, content_index)
                self.field_roles[field_id] = role
                self.field_styles[field_id] = self._complete_field_style(
                    saved_style,
                    getattr(project, f"{role}_background_color"),
                    getattr(project, f"{role}_text_color"),
                )
                if field_type != "shape":
                    self.field_styles[field_id].update(
                        {"shape": "rectangle", "inset": "0", "corner_radius": "0"}
                    )
                content_index += 1
            list_item = QListWidgetItem(self._field_list_text(field_data))
            list_item.setData(Qt.ItemDataRole.UserRole, field_id)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, field_type)
            list_item.setData(
                Qt.ItemDataRole.UserRole + 2,
                self.field_styles[field_id].get("parent_id", ""),
            )
            list_item.setToolTip(
                "Drop onto an image to overlay it; drop between rows to detach"
            )
            self.field_order_list.addItem(list_item)
        self._sync_order_item_hierarchy()

        self.content_group = QGroupBox()
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
        self.image_gradient_label = QLabel("Image gradient")
        self.image_gradient_combo = QComboBox()
        for label, value in (
            ("None", "none"),
            ("Bottom fade", "bottom"),
            ("Top fade", "top"),
            ("Left fade", "left"),
            ("Right fade", "right"),
            ("Full tint", "tint"),
        ):
            self.image_gradient_combo.addItem(label, value)
        self.image_gradient_color_label = QLabel("Gradient color")
        self.image_gradient_color_button = ColorButton("#000000")
        self.image_gradient_opacity_label = QLabel("Gradient opacity")
        self.image_gradient_opacity_spin = QSpinBox()
        self.image_gradient_opacity_spin.setRange(0, 100)
        self.image_gradient_opacity_spin.setSuffix(" %")
        content_form.addRow("Label", self.field_label_edit)
        content_form.addRow("Value", self.field_value_edit)
        content_form.addRow("", self.field_browse_button)
        content_form.addRow(self.image_height_label, self.image_height_spin)
        content_form.addRow(self.image_gradient_label, self.image_gradient_combo)
        content_form.addRow(
            self.image_gradient_color_label, self.image_gradient_color_button
        )
        content_form.addRow(
            self.image_gradient_opacity_label, self.image_gradient_opacity_spin
        )
        controls_layout.addWidget(self.content_group)

        self.style_group = QGroupBox()
        self.style_group.setObjectName("DesignerSection")
        style_form = QFormLayout(self.style_group)
        style_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.band_background_button = ColorButton("#111827")
        self.band_fill_combo = QComboBox()
        for label, value in (
            ("Solid", "solid"),
            ("Top to bottom", "vertical"),
            ("Bottom to top", "vertical_reverse"),
            ("Left to right", "horizontal"),
            ("Right to left", "horizontal_reverse"),
            ("Top-left to bottom-right", "diagonal"),
            ("Bottom-right to top-left", "diagonal_reverse"),
            ("Bottom-left to top-right", "diagonal_up"),
            ("Top-right to bottom-left", "diagonal_up_reverse"),
        ):
            self.band_fill_combo.addItem(label, value)
        self.band_gradient_button = ColorButton("#111827", allow_alpha=True)
        gradient_opacity_row = QWidget()
        gradient_opacity_layout = QHBoxLayout(gradient_opacity_row)
        gradient_opacity_layout.setContentsMargins(0, 0, 0, 0)
        gradient_opacity_layout.setSpacing(8)
        self.band_gradient_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.band_gradient_opacity_slider.setRange(0, 100)
        self.band_gradient_opacity_slider.setValue(100)
        self.band_gradient_opacity_slider.setToolTip(
            "0% makes the gradient end fully transparent; 100% is fully opaque."
        )
        self.band_gradient_opacity_value = QLabel("100%")
        self.band_gradient_opacity_value.setMinimumWidth(42)
        self.band_gradient_opacity_value.setAlignment(Qt.AlignmentFlag.AlignRight)
        gradient_opacity_layout.addWidget(self.band_gradient_opacity_slider, 1)
        gradient_opacity_layout.addWidget(self.band_gradient_opacity_value)
        self.band_text_button = ColorButton("#ffffff")
        self.band_outline_button = ColorButton("#000000")
        self.band_outline_width_spin = QSpinBox()
        self.band_outline_width_spin.setRange(0, 8)
        self.band_outline_width_spin.setSuffix(" px")
        self.band_outline_width_spin.setSpecialValueText("None")
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
        self.band_padding_spin = QSpinBox()
        self.band_padding_spin.setRange(0, 64)
        self.band_padding_spin.setSuffix(" px")
        style_form.addRow("Background", self.band_background_button)
        style_form.addRow("Gradient direction", self.band_fill_combo)
        style_form.addRow("Gradient end", self.band_gradient_button)
        style_form.addRow("End opacity", gradient_opacity_row)
        style_form.addRow("Text", self.band_text_button)
        style_form.addRow("Text outline", self.band_outline_button)
        style_form.addRow("Outline width", self.band_outline_width_spin)
        style_form.addRow("Alignment", self.band_alignment_combo)
        style_form.addRow("Font weight", self.band_font_weight_combo)
        style_form.addRow("Font size", self.band_font_size_spin)
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
        self.box_preview = BoxStylePreview(
            self._image_item,
            self.project.height,
            project_width=self.project.width,
        )
        self.box_preview.image_clicked.connect(self._edit_image)
        self.box_preview.field_selected.connect(self._preview_field_selected)
        self.box_preview.item_dropped.connect(self._preview_item_dropped)
        self.box_preview.image_file_dropped.connect(self._preview_image_dropped)
        self.box_preview.delete_requested.connect(self._remove_selected_content)
        self.box_preview.field_reorder_requested.connect(
            self._preview_field_reorder_requested
        )
        self.box_preview.layer_order_requested.connect(
            self._preview_layer_order_requested
        )
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.box_preview, 1)
        preview_help = QLabel(
            "Drag an icon onto the preview to add it. Select, move, and resize "
            "objects with the handles; right-click to change layer order; press "
            "Delete to remove the selected item."
        )
        preview_help.setObjectName("DesignerHint")
        preview_help.setWordWrap(True)
        preview_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(preview_help)
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
        self.image_height_slider.valueChanged.connect(self._update_preview)
        self.image_fit_combo.currentIndexChanged.connect(self._update_preview)
        self.text_font_combo.currentFontChanged.connect(self._update_preview)
        self.text_font_size_spin.valueChanged.connect(self._update_preview)
        self.apply_preset_button.clicked.connect(self._apply_selected_preset)
        self.save_preset_button.clicked.connect(self._save_custom_preset)
        self.delete_preset_button.clicked.connect(self._delete_custom_preset)
        self.border_color_button.color_changed.connect(self._update_preview)
        self.border_width_spin.valueChanged.connect(self._update_preview)
        self.snap_objects_check.toggled.connect(self._update_preview)
        self.field_order_list.itemSelectionChanged.connect(self._load_selected_field_style)
        self.field_order_list.model().rowsMoved.connect(self._field_order_changed)
        self.field_order_list.add_requested.connect(self._show_add_item_menu)
        self.field_order_list.delete_requested.connect(self._remove_selected_content)
        self.field_order_list.hierarchy_drop_requested.connect(
            self._hierarchy_drop_requested
        )
        self._loading_field_content = False
        self.field_label_edit.textEdited.connect(self._selected_field_content_changed)
        self.field_value_edit.textEdited.connect(self._selected_field_content_changed)
        self.field_browse_button.clicked.connect(self._browse_selected_image)
        self.image_height_spin.valueChanged.connect(self._selected_image_height_changed)
        self.image_gradient_combo.currentIndexChanged.connect(
            self._selected_image_gradient_changed
        )
        self.image_gradient_color_button.color_changed.connect(
            self._selected_image_gradient_changed
        )
        self.image_gradient_opacity_spin.valueChanged.connect(
            self._selected_image_gradient_changed
        )
        self._loading_field_style = False
        self.band_background_button.color_changed.connect(self._selected_field_style_changed)
        self.band_fill_combo.currentIndexChanged.connect(self._selected_field_style_changed)
        self.band_gradient_button.color_changed.connect(
            self._band_gradient_color_changed
        )
        self.band_gradient_opacity_slider.valueChanged.connect(
            self._band_gradient_opacity_changed
        )
        self.band_text_button.color_changed.connect(self._selected_field_style_changed)
        self.band_outline_button.color_changed.connect(self._selected_field_style_changed)
        self.band_outline_width_spin.valueChanged.connect(self._selected_field_style_changed)
        self.band_alignment_combo.currentIndexChanged.connect(self._selected_field_style_changed)
        self.band_font_weight_combo.currentIndexChanged.connect(self._selected_field_style_changed)
        self.band_font_size_spin.valueChanged.connect(self._selected_field_style_changed)
        self.band_padding_spin.valueChanged.connect(self._selected_field_style_changed)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if self.field_order_list.count():
            self.field_order_list.setCurrentRow(0)
        self._load_values()

    @staticmethod
    def _set_form_row_visible(form: QFormLayout, field: QWidget, visible: bool) -> None:
        label = form.labelForField(field)
        if label is not None:
            label.setVisible(visible)
        field.setVisible(visible)

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
        if isinstance(raw_value, dict):
            parsed = raw_value
        else:
            try:
                parsed = json.loads(str(raw_value or "{}"))
            except (json.JSONDecodeError, TypeError, ValueError):
                return {}
        if not isinstance(parsed, dict):
            return {}
        presets: dict[str, dict[str, object]] = {}
        for name, preset in parsed.items():
            if isinstance(preset, dict):
                presets[str(name)] = self._normalize_preset(preset)
        return presets

    def _save_custom_presets_to_preferences(self) -> bool:
        self.preferences.setValue(
            "box_style_presets",
            json.dumps(self.custom_presets, sort_keys=True),
        )
        # QSettings may otherwise defer the native-file/registry write until the
        # dialog is destroyed, which can lose a just-saved preset on app exit.
        self.preferences.sync()
        return self.preferences.status() == QSettings.Status.NoError

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
        border_width = self._bounded_int(preset.get("border_width"), 3, 0, 40)
        try:
            preview_columns = int(preset.get("preview_columns") or 0)
        except (TypeError, ValueError):
            preview_columns = 0
        if not MIN_PREVIEW_COLUMNS_1080P <= preview_columns <= MAX_PREVIEW_COLUMNS_1080P:
            preview_columns = 0
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
                    "container_color": self._valid_color(
                        style.get("container_color"),
                        self._valid_color(style.get("background_color"), "#111827"),
                    ),
                    "inset": str(self._bounded_int(style.get("inset"), 0, 0, 96)),
                    "corner_radius": str(
                        self._bounded_int(style.get("corner_radius"), 0, 0, 64)
                    ),
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
                    "shape": normalized_shape(style.get("shape")),
                    "fill_mode": (
                        str(style.get("fill_mode"))
                        if str(style.get("fill_mode")) in FILL_OPTIONS
                        else "solid"
                    ),
                    "gradient_color_2": self._valid_color(
                        style.get("gradient_color_2"),
                        self._valid_color(style.get("background_color"), "#111827"),
                    ),
                }
        normalized_objects: list[dict[str, object]] = []
        objects = preset.get("objects")
        if isinstance(objects, list):
            valid_types = {"image", "name", "text", "number", "shape"}
            for index, raw_object in enumerate(objects):
                if not isinstance(raw_object, dict):
                    continue
                field_type = str(raw_object.get("type") or "text")
                if field_type not in valid_types:
                    field_type = "text"
                role = str(raw_object.get("role") or "")
                raw_style = raw_object.get("style")
                raw_style = raw_style if isinstance(raw_style, dict) else {}
                if field_type == "image":
                    object_style = self._complete_image_style(raw_style)
                else:
                    fallback_role = role if role in {"name", "category", "rank", "value"} else "category"
                    object_style = self._complete_field_style(
                        raw_style,
                        str(getattr(self.project, f"{fallback_role}_background_color")),
                        str(getattr(self.project, f"{fallback_role}_text_color")),
                    )
                try:
                    parent_index = int(raw_object.get("parent_index", -1))
                except (TypeError, ValueError):
                    parent_index = -1
                if parent_index < 0 or parent_index >= len(objects) or parent_index == index:
                    parent_index = -1
                object_style["parent_id"] = ""
                normalized_objects.append(
                    {
                        "type": field_type,
                        "role": role,
                        "label": str(raw_object.get("label") or field_type.title()),
                        "value": (
                            str(raw_object.get("value") or "")
                            if field_type == "shape" else ""
                        ),
                        "parent_index": parent_index,
                        "style": object_style,
                    }
                )
        return {
            "version": 2 if normalized_objects else 1,
            "border_color": self._valid_color(preset.get("border_color"), "#05070a"),
            "border_width": border_width,
            "text_font_family": str(preset.get("text_font_family") or "Segoe UI"),
            "text_font_size": font_size,
            "preview_columns": preview_columns,
            "image_fit": fit,
            "image_height_percent": max(35, min(75, image_height)),
            "layout_template": str(preset.get("layout_template") or ""),
            "roles": normalized_roles,
            "objects": normalized_objects,
        }

    def _valid_color(self, value: object, fallback: str) -> str:
        color = QColor(str(value or ""))
        if not color.isValid():
            return fallback
        color_format = (
            QColor.NameFormat.HexArgb
            if color.alpha() < 255
            else QColor.NameFormat.HexRgb
        )
        return color.name(color_format)

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
            "container_color": self._valid_color(
                raw.get("container_color"),
                self._valid_color(raw.get("background_color"), background),
            ),
            "inset": str(self._bounded_int(raw.get("inset"), 0, 0, 96)),
            "corner_radius": str(
                self._bounded_int(raw.get("corner_radius"), 0, 0, 64)
            ),
            "alignment": alignment,
            "font_size": str(self._bounded_int(raw.get("font_size"), 0, 0, 120)),
            "height_weight": str(self._bounded_int(raw.get("height_weight"), 100, 25, 400)),
            "padding": str(self._bounded_int(raw.get("padding"), 14, 0, 64)),
            "font_weight": str(weight),
            "parent_id": str(raw.get("parent_id") or ""),
            "shape": normalized_shape(raw.get("shape")),
            "fill_mode": str(raw.get("fill_mode") or "solid")
            if str(raw.get("fill_mode") or "solid") in FILL_OPTIONS
            else "solid",
            "gradient_color_2": self._valid_color(
                raw.get("gradient_color_2"),
                self._valid_color(raw.get("background_color"), background),
            ),
            "overlay_x": self._overlay_value(raw.get("overlay_x"), 0),
            "overlay_y": self._overlay_value(raw.get("overlay_y"), 0),
            "overlay_width": self._overlay_value(raw.get("overlay_width"), 20),
            "overlay_height": self._overlay_value(raw.get("overlay_height"), 20),
        }

    @staticmethod
    def _overlay_value(value: object, minimum: int) -> str:
        if value in (None, ""):
            return ""
        try:
            number = int(value)
        except (TypeError, ValueError):
            return ""
        return str(max(minimum, min(1000, number)))

    def _complete_image_style(self, style: dict[str, str] | object) -> dict[str, str]:
        raw = style if isinstance(style, dict) else {}
        gradient_mode = str(raw.get("gradient_mode") or "none")
        if gradient_mode not in {"none", "bottom", "top", "left", "right", "tint"}:
            gradient_mode = "none"
        return {
            "height_weight": str(
                self._bounded_int(raw.get("height_weight"), 100, 25, 400)
            ),
            "parent_id": "",
            "gradient_mode": gradient_mode,
            "gradient_color": self._valid_color(
                raw.get("gradient_color"), "#000000"
            ),
            "gradient_opacity": str(
                self._bounded_int(raw.get("gradient_opacity"), 65, 0, 100)
            ),
            "shape": normalized_shape(raw.get("shape")),
            "overlay_x": self._overlay_value(raw.get("overlay_x"), 0),
            "overlay_y": self._overlay_value(raw.get("overlay_y"), 0),
            "overlay_width": self._overlay_value(raw.get("overlay_width"), 20),
            "overlay_height": self._overlay_value(raw.get("overlay_height"), 20),
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
        preset_data = str(self.preset_combo.currentData() or "")
        preview_columns = int(preset.get("preview_columns") or 0)
        if preview_columns:
            columns_index = self.columns_combo.findData(preview_columns)
            if columns_index >= 0:
                self.columns_combo.setCurrentIndex(columns_index)
        self.image_height_slider.setValue(int(preset["image_height_percent"]))
        fit_index = self.image_fit_combo.findData(str(preset["image_fit"]))
        if fit_index >= 0:
            self.image_fit_combo.setCurrentIndex(fit_index)
        self.text_font_combo.setCurrentFont(QFont(str(preset["text_font_family"])))
        self.text_font_size_spin.setValue(int(preset["text_font_size"]))
        self.border_color_button.set_color(str(preset["border_color"]))
        self.border_width_spin.setValue(int(preset["border_width"]))
        self._apply_layout_template(str(preset.get("layout_template") or ""))
        objects = preset.get("objects", [])
        if preset_data.startswith("custom:") and isinstance(objects, list) and objects:
            self._apply_custom_preset_objects(objects)
            self._load_selected_field_style()
            self._update_preview()
            return
        role_styles = preset.get("roles", {})
        if isinstance(role_styles, dict):
            for field_id in self.field_roles:
                role = self.field_roles.get(field_id, "category")
                style = role_styles.get(role)
                if not isinstance(style, dict):
                    continue
                current = self.field_styles[field_id]
                updated = self._complete_field_style(
                    style,
                    current["background_color"],
                    current["text_color"],
                )
                updated["parent_id"] = current.get("parent_id", "")
                for key in (
                    "overlay_x",
                    "overlay_y",
                    "overlay_width",
                    "overlay_height",
                ):
                    updated[key] = current.get(key, "")
                self.field_styles[field_id] = updated
        self._load_selected_field_style()
        self._update_preview()

    def _apply_custom_preset_objects(self, objects: list[dict[str, object]]) -> None:
        """Map a saved visual object layout onto the current project's inputs."""
        fields = self._image_item.display_fields()
        by_id = {str(field.get("id", "")): field for field in fields}
        unused_ids = [str(field.get("id", "")) for field in fields]
        object_to_field: dict[int, str] = {}
        pending_transforms: dict[str, dict[str, float | str]] = {}

        for object_index, preset_object in enumerate(objects):
            field_type = str(preset_object.get("type") or "text")
            role = str(preset_object.get("role") or "")
            candidates = [by_id[field_id] for field_id in unused_ids]
            match = next(
                (
                    field
                    for field in candidates
                    if str(field.get("type") or "text") == field_type
                    and role
                    and str(field.get("role") or "") == role
                ),
                None,
            )
            if match is None:
                match = next(
                    (
                        field
                        for field in candidates
                        if str(field.get("type") or "text") == field_type
                    ),
                    None,
                )
            if match is None:
                source = next(
                    (
                        field
                        for field in fields
                        if field_type != "shape"
                        and str(field.get("type") or "text") == field_type
                    ),
                    None,
                )
                source_id = str(source.get("id", "")) if source else ""
                field_id = f"field_{uuid4().hex[:8]}"
                match = dict(source) if source is not None else {}
                match.update(
                    {
                        "id": field_id,
                        "type": field_type,
                        "role": role,
                        "label": str(preset_object.get("label") or field_type.title()),
                        "value": (
                            str(preset_object.get("value") or "")
                            if field_type == "shape"
                            else str(match.get("value") or "")
                        ),
                    }
                )
                fields.append(match)
                by_id[field_id] = match
                self.field_types[field_id] = field_type
                if field_type != "image":
                    fallback_role = role if role in {"name", "category", "rank", "value"} else "category"
                    self.field_roles[field_id] = fallback_role
                self._new_field_sources[field_id] = source_id
                source_transform = self._image_item.image_transforms.get(source_id)
                if source_transform is not None:
                    pending_transforms[field_id] = dict(source_transform)
            field_id = str(match.get("id", ""))
            if field_id in unused_ids:
                unused_ids.remove(field_id)
            object_to_field[object_index] = field_id
            raw_style = preset_object.get("style")
            raw_style = raw_style if isinstance(raw_style, dict) else {}
            current = self.field_styles.get(field_id, {})
            if field_type == "image":
                self.field_styles[field_id] = self._complete_image_style(raw_style)
            else:
                self.field_styles[field_id] = self._complete_field_style(
                    raw_style,
                    str(current.get("background_color") or "#111827"),
                    str(current.get("text_color") or "#ffffff"),
                )
                if field_type != "shape":
                    self.field_styles[field_id]["shape"] = "rectangle"

        for object_index, field_id in object_to_field.items():
            if self.field_types.get(field_id) == "image":
                self.field_styles[field_id]["parent_id"] = ""
                continue
            try:
                parent_index = int(objects[object_index].get("parent_index", -1))
            except (TypeError, ValueError):
                parent_index = -1
            parent_id = object_to_field.get(parent_index, "")
            if self.field_types.get(parent_id) != "image":
                parent_id = ""
            self.field_styles[field_id]["parent_id"] = parent_id

        selected_id = self._selected_field_id()
        ordered_ids = [
            object_to_field[index]
            for index in range(len(objects))
            if index in object_to_field
        ]
        self._image_item.set_fields([by_id[field_id] for field_id in ordered_ids])
        self._image_item.image_transforms.update(pending_transforms)
        self.field_styles = {
            field_id: self.field_styles[field_id] for field_id in ordered_ids
        }
        self.field_types = {
            field_id: self.field_types[field_id] for field_id in ordered_ids
        }
        self.field_roles = {
            field_id: role
            for field_id, role in self.field_roles.items()
            if field_id in object_to_field.values()
        }
        self._new_field_sources = {
            field_id: source_id
            for field_id, source_id in self._new_field_sources.items()
            if field_id in object_to_field.values()
        }
        if selected_id not in ordered_ids:
            selected_id = ordered_ids[0] if ordered_ids else ""
        self._rebuild_order_list(ordered_ids, selected_id)

    def _apply_layout_template(self, template_name: str) -> None:
        if template_name != "hall_of_fame":
            return
        fields = self._image_item.display_fields()

        def first_field(*, field_type: str = "", role: str = ""):
            return next(
                (
                    field
                    for field in fields
                    if (not field_type or field.get("type") == field_type)
                    and (not role or field.get("role") == role)
                ),
                None,
            )

        name_field = first_field(field_type="name") or {
            "id": "field_name",
            "type": "name",
            "label": "Name",
            "value": self._image_item.name,
            "role": "name",
        }
        portrait_field = first_field(field_type="image") or {
            "id": "field_image",
            "type": "image",
            "label": "Portrait",
            "value": "",
            "role": "image",
        }
        team_field = first_field(role="category") or {
            "id": "field_team",
            "type": "text",
            "label": "Team",
            "value": self._image_item.category,
            "role": "category",
        }
        year_field = first_field(role="rank") or first_field(role="value") or {
            "id": "field_year",
            "type": "number",
            "label": "Year",
            "value": self._image_item.rank,
            "role": "rank",
        }
        other_images = [
            field
            for field in fields
            if field.get("type") == "image"
            and str(field.get("id", "")) != str(portrait_field.get("id", ""))
        ]
        logo_is_new = not other_images
        logo_field = other_images[0] if other_images else {
            "id": f"field_{uuid4().hex[:8]}",
            "type": "image",
            "label": "Team logo",
            "value": "",
            "role": "image",
        }

        name_field = dict(name_field)
        portrait_field = dict(portrait_field)
        team_field = dict(team_field)
        logo_field = dict(logo_field)
        year_field = dict(year_field)
        name_field.update({"label": "Name", "type": "name", "role": "name"})
        portrait_field.update({"label": "Portrait", "type": "image", "role": "image"})
        team_field.update({"label": "Team", "type": "text", "role": "category"})
        logo_field.update({"label": "Team logo", "type": "image", "role": "image"})
        year_field.update({"label": "Year", "type": "number", "role": "rank"})
        template_fields = [
            name_field,
            portrait_field,
            team_field,
            logo_field,
            year_field,
        ]
        self._image_item.set_fields(template_fields)

        active_ids = {str(field.get("id", "")) for field in template_fields}
        self.field_styles = {
            field_id: style
            for field_id, style in self.field_styles.items()
            if field_id in active_ids
        }
        self.field_roles.clear()
        self.field_types.clear()
        self._new_field_sources.clear()
        self.field_order_list.clear()
        content_index = 0
        for field in template_fields:
            field_id = str(field.get("id", ""))
            field_type = str(field.get("type", "text"))
            self.field_types[field_id] = field_type
            if field_type == "image":
                self.field_styles[field_id] = self._complete_image_style(
                    self.field_styles.get(field_id, {})
                )
            else:
                role = self._field_role(field, content_index)
                self.field_roles[field_id] = role
                self.field_styles.setdefault(
                    field_id,
                    self._complete_field_style(
                        {},
                        getattr(self.project, f"{role}_background_color"),
                        getattr(self.project, f"{role}_text_color"),
                    ),
                )
                content_index += 1
            list_item = QListWidgetItem(self._field_list_text(field))
            list_item.setData(Qt.ItemDataRole.UserRole, field_id)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, field_type)
            list_item.setData(
                Qt.ItemDataRole.UserRole + 2,
                self.field_styles[field_id].get("parent_id", ""),
            )
            list_item.setToolTip(
                "Drop onto an image to overlay it; drop between rows to detach"
            )
            self.field_order_list.addItem(list_item)

        portrait_id = str(portrait_field.get("id", ""))
        logo_id = str(logo_field.get("id", ""))
        self.field_styles[portrait_id]["height_weight"] = "78"
        self.field_styles[logo_id]["height_weight"] = "22"
        if logo_is_new:
            self._new_field_sources[logo_id] = ""
        self._sync_order_item_hierarchy()
        self.field_order_list.setCurrentRow(0)

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
        if not self._save_custom_presets_to_preferences():
            QMessageBox.warning(
                self,
                "Save Custom Preset",
                "The preset could not be written to your application settings.",
            )
            return
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
        fields = self._image_item.display_fields()
        index_by_id = {
            str(field.get("id", "")): index for index, field in enumerate(fields)
        }
        objects: list[dict[str, object]] = []
        for field in fields:
            field_id = str(field.get("id", ""))
            style = dict(self.field_styles.get(field_id, {}))
            parent_id = str(style.pop("parent_id", "") or "")
            objects.append(
                {
                    "type": str(field.get("type") or "text"),
                    "role": str(field.get("role") or ""),
                    "label": str(field.get("label") or "Input"),
                    "value": (
                        str(field.get("value") or "")
                        if field.get("type") == "shape" else ""
                    ),
                    "parent_index": index_by_id.get(parent_id, -1),
                    "style": style,
                }
            )
        return {
            "version": 2,
            "border_color": self.border_color_button.color(),
            "border_width": self.border_width_spin.value(),
            "text_font_family": self.text_font_combo.currentFont().family(),
            "text_font_size": self.text_font_size_spin.value(),
            "preview_columns": int(self.columns_combo.currentData()),
            "image_fit": str(self.image_fit_combo.currentData() or "cover"),
            "image_height_percent": int(self.image_height_slider.value()),
            "roles": roles,
            "objects": objects,
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
        self.project.card_border_color = self.border_color_button.color()
        self.project.card_border_width = self.border_width_spin.value()
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
                    if field.get("type") == "image" and field_id in self._all_box_image_updates:
                        field["value"] = self._all_box_image_updates[field_id][0]
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
            image_ids = {field["id"] for field in fields if field.get("type") == "image"}
            for field_id, (_path, transform) in self._all_box_image_updates.items():
                if field_id not in image_ids:
                    continue
                if existing_item is self.item:
                    transform = self._image_item.image_transforms.get(field_id, transform)
                existing_item.image_transforms[field_id] = dict(transform)
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
        frame = image_field_frame_size(
            fields,
            field_id,
            self.field_styles,
            QSize(self.project.width // columns, self.project.height),
            self.image_height_slider.value(),
        )
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
        if dialog.apply_to_all_boxes:
            self._all_box_image_updates[field_id] = (dialog.image_path, dialog.image_transform())
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
        self.border_width_spin.setValue(self.project.card_border_width)
        width = self.project.width // columns
        self.box_size_label.setText(f"{width} x {self.project.height} px per box")
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
            self.snap_objects_check.isChecked(),
            border_width=self.border_width_spin.value(),
        )

    def _selected_field_id(self) -> str:
        item = self.field_order_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "") if item else ""

    @staticmethod
    def _field_type_label(field_type: str) -> str:
        if field_type == "image":
            return "IMAGE"
        if field_type == "shape":
            return "SHAPE"
        return "TEXT"

    def _field_list_text(self, field: dict[str, str]) -> str:
        field_type = str(field.get("type", "text"))
        type_label = self._field_type_label(field_type)
        value = str(field.get("value") or "").strip()
        if field_type == "image" and value:
            value = Path(value).name
        label = value or str(field.get("label") or "Input").strip()
        if len(label) > 34:
            label = f"{label[:31]}..."
        return f"{type_label}  ·  {label}"

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
        field_type = str(field_data.get("type", "")) if field_data else ""
        is_text = field_type in {"text", "name", "number", "shape"}
        content_form = self.content_group.layout()
        if isinstance(content_form, QFormLayout):
            self._set_form_row_visible(content_form, self.field_label_edit, is_text)
            self._set_form_row_visible(content_form, self.field_value_edit, is_text)
            self._set_form_row_visible(content_form, self.field_browse_button, is_image)
        else:
            self.field_label_edit.setVisible(is_text)
            self.field_value_edit.setVisible(is_text)
            self.field_browse_button.setVisible(is_image)
        image_style = self.field_styles.get(field_id, {})
        self.image_height_spin.setValue(
            self._bounded_int(image_style.get("height_weight"), 100, 25, 400)
        )
        gradient_index = self.image_gradient_combo.findData(
            image_style.get("gradient_mode", "none")
        )
        self.image_gradient_combo.setCurrentIndex(max(0, gradient_index))
        self.image_gradient_color_button.set_color(
            str(image_style.get("gradient_color") or "#000000")
        )
        self.image_gradient_opacity_spin.setValue(
            self._bounded_int(image_style.get("gradient_opacity"), 65, 0, 100)
        )
        self.image_height_label.setVisible(is_image)
        self.image_height_spin.setVisible(is_image)
        self.image_gradient_label.setVisible(is_image)
        self.image_gradient_combo.setVisible(is_image)
        self.image_gradient_color_label.setVisible(is_image)
        self.image_gradient_color_button.setVisible(is_image)
        self.image_gradient_opacity_label.setVisible(is_image)
        self.image_gradient_opacity_spin.setVisible(is_image)
        self.content_group.setEnabled(field_data is not None)
        self.content_group.setVisible(is_text or is_image)
        self._loading_field_content = False
        style = self.field_styles.get(field_id)
        if style is None or is_image:
            self.style_group.setEnabled(False)
            self.style_group.setVisible(False)
            return
        self.style_group.setEnabled(True)
        self.style_group.setVisible(True)
        self._loading_field_style = True
        self.band_background_button.set_color(style["background_color"])
        self.band_fill_combo.setCurrentIndex(
            max(0, self.band_fill_combo.findData(style.get("fill_mode", "solid")))
        )
        gradient_end = style.get("gradient_color_2", style["background_color"])
        self.band_gradient_button.set_color(gradient_end)
        gradient_alpha = QColor(gradient_end).alpha()
        gradient_opacity = round(gradient_alpha * 100 / 255)
        self.band_gradient_opacity_slider.setValue(gradient_opacity)
        self.band_gradient_opacity_value.setText(f"{gradient_opacity}%")
        self.band_text_button.set_color(style["text_color"])
        self.band_outline_button.set_color(style["outline_color"])
        self.band_outline_width_spin.setValue(int(style["outline_width"]))
        self.band_alignment_combo.setCurrentIndex(
            max(0, self.band_alignment_combo.findData(style["alignment"]))
        )
        self.band_font_weight_combo.setCurrentIndex(
            max(0, self.band_font_weight_combo.findData(int(style["font_weight"])))
        )
        self.band_font_size_spin.setValue(int(style["font_size"]))
        self.band_padding_spin.setValue(int(style["padding"]))
        self._loading_field_style = False

    def _band_gradient_color_changed(self, color_value: str) -> None:
        color = QColor(color_value)
        opacity = round(color.alpha() * 100 / 255) if color.isValid() else 100
        self.band_gradient_opacity_value.setText(f"{opacity}%")
        if self.band_gradient_opacity_slider.value() != opacity:
            was_loading = self._loading_field_style
            self._loading_field_style = True
            self.band_gradient_opacity_slider.setValue(opacity)
            self._loading_field_style = was_loading
        self._selected_field_style_changed()

    def _band_gradient_opacity_changed(self, opacity: int) -> None:
        self.band_gradient_opacity_value.setText(f"{opacity}%")
        if self._loading_field_style:
            return
        color = QColor(self.band_gradient_button.color())
        if not color.isValid():
            color = QColor("#111827")
        color.setAlpha(round(255 * opacity / 100))
        color_format = (
            QColor.NameFormat.HexRgb
            if opacity == 100
            else QColor.NameFormat.HexArgb
        )
        self._loading_field_style = True
        self.band_gradient_button.set_color(color.name(color_format))
        self._loading_field_style = False
        self._selected_field_style_changed()

    def _selected_field_style_changed(self, *_args) -> None:
        if self._loading_field_style:
            return
        field_id = self._selected_field_id()
        if not field_id:
            return
        previous_style = self.field_styles.get(field_id, {})
        parent_id = previous_style.get("parent_id", "")
        self.field_styles[field_id] = {
            "background_color": self.band_background_button.color(),
            "fill_mode": str(self.band_fill_combo.currentData() or "solid"),
            "gradient_color_2": self.band_gradient_button.color(),
            "container_color": "",
            "text_color": self.band_text_button.color(),
            "outline_color": self.band_outline_button.color(),
            "outline_width": str(self.band_outline_width_spin.value()),
            "border_color": "#000000",
            "border_width": "0",
            "alignment": str(self.band_alignment_combo.currentData() or "center"),
            "font_weight": str(self.band_font_weight_combo.currentData() or 700),
            "font_size": str(self.band_font_size_spin.value()),
            "height_weight": "100",
            "padding": str(self.band_padding_spin.value()),
            "inset": "0",
            "corner_radius": "0",
            "parent_id": parent_id,
            "shape": previous_style.get("shape", "rectangle"),
            "overlay_x": previous_style.get("overlay_x", ""),
            "overlay_y": previous_style.get("overlay_y", ""),
            "overlay_width": previous_style.get("overlay_width", ""),
            "overlay_height": previous_style.get("overlay_height", ""),
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
            current_item.setText(self._field_list_text(field))
        self._update_preview()

    def _selected_image_height_changed(self, value: int) -> None:
        if self._loading_field_content:
            return
        field_id = self._selected_field_id()
        if self.field_types.get(field_id) != "image":
            return
        self.field_styles.setdefault(field_id, {})["height_weight"] = str(value)
        self._update_preview()

    def _selected_image_gradient_changed(self, *_args) -> None:
        if self._loading_field_content:
            return
        field_id = self._selected_field_id()
        if self.field_types.get(field_id) != "image":
            return
        style = self.field_styles.setdefault(
            field_id, self._complete_image_style({})
        )
        style["gradient_mode"] = str(
            self.image_gradient_combo.currentData() or "none"
        )
        style["gradient_color"] = self.image_gradient_color_button.color()
        style["gradient_opacity"] = str(
            self.image_gradient_opacity_spin.value()
        )
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
        for style in self.field_styles.values():
            if style.get("parent_id") == field_id:
                style["parent_id"] = ""
        self.field_roles.pop(field_id, None)
        self.field_types.pop(field_id, None)
        self._new_field_sources.pop(field_id, None)
        removed_item = self.field_order_list.takeItem(row)
        del removed_item
        self.field_order_list.setCurrentRow(
            min(row, self.field_order_list.count() - 1)
        )
        self._sync_order_item_hierarchy()
        self._update_preview()

    def _palette_item_activated(self, item_kind: str) -> None:
        self._add_content_item(self._selected_field_id(), item_kind)

    def _preview_item_dropped(self, item_kind: str, position: QPoint) -> None:
        self._add_content_item(self._selected_field_id(), item_kind, position)

    def _preview_image_dropped(self, path: str, position: QPoint) -> None:
        self._add_content_item(
            self._selected_field_id(), "image", position, image_path=path
        )

    def _show_add_item_menu(self, source_id: str = "") -> None:
        if source_id:
            self._preview_field_selected(source_id)
        menu = QMenu(self)
        options = (
            ("Text", "text"),
            ("Image", "image"),
            ("Rectangle", "rectangle"),
            ("Rounded rectangle", "rounded"),
            ("Pill", "pill"),
            ("Circle", "circle"),
            ("Ellipse", "ellipse"),
            ("Triangle", "triangle"),
            ("Down triangle", "triangle_down"),
            ("Diamond", "diamond"),
            ("Pentagon", "pentagon"),
            ("Hexagon", "hexagon"),
            ("Octagon", "octagon"),
            ("Star", "star"),
            ("Burst", "burst"),
            ("Chevron", "chevron"),
            ("Left arrow", "arrow_left"),
            ("Right arrow", "arrow_right"),
            ("Parallelogram", "parallelogram"),
            ("Trapezoid", "trapezoid"),
            ("Cross", "cross"),
            ("Heart", "heart"),
        )
        for label, item_kind in options:
            action = menu.addAction(label)
            action.setData(item_kind)
        current_item = self.field_order_list.currentItem()
        menu_position = self.field_order_list.mapToGlobal(
            self.field_order_list.visualItemRect(current_item).bottomLeft()
            if current_item is not None
            else self.field_order_list.rect().center()
        )
        chosen = menu.exec(menu_position)
        if chosen is not None:
            self._add_content_item(source_id, str(chosen.data() or "text"))

    @staticmethod
    def _default_insert_index(
        fields: list[dict[str, str]],
        source_id: str,
        item_kind: str,
    ) -> int:
        if item_kind == "image" and not any(
            str(field.get("type", "")) == "image" for field in fields
        ):
            return 0
        return next(
            (
                index + 1
                for index, field in enumerate(fields)
                if str(field.get("id", "")) == source_id
            ),
            len(fields),
        )

    def _add_content_item(
        self,
        source_id: str,
        item_kind: str,
        drop_position: QPoint | None = None,
        image_path: str = "",
    ) -> str:
        fields = self._image_item.display_fields()
        insert_index = self._default_insert_index(fields, source_id, item_kind)
        new_id = f"field_{uuid4().hex[:8]}"
        is_image = item_kind == "image"
        is_shape = item_kind not in {"text", "image"}
        if is_image:
            label = Path(image_path).stem or "Image"
            field_type = "image"
        else:
            label = item_kind.replace("_", " ").title() if is_shape else "Text"
            field_type = "shape" if is_shape else "text"
        new_field = {
            "id": new_id,
            "type": field_type,
            "label": label,
            "value": image_path if is_image else "Text",
            "role": "image" if is_image else "",
        }
        fields.insert(insert_index, new_field)
        self._image_item.set_fields(fields)
        self.field_types[new_id] = field_type
        if not is_image:
            self.field_roles[new_id] = "category"
        self._new_field_sources[new_id] = ""
        if is_image:
            style = self._complete_image_style({})
            width, height = 760, 420
            self._images_changed = True
        else:
            style = self._complete_field_style({}, "#2563eb", "#ffffff")
            style["shape"] = normalized_shape(item_kind if is_shape else "rectangle")
            width, height = (700, 160) if not is_shape else (700, 220)
        if item_kind == "circle":
            width, height = 350, 207
        elif item_kind in {
            "triangle", "triangle_down", "diamond", "pentagon", "hexagon",
            "octagon", "star", "burst", "cross", "heart",
        }:
            width, height = 520, 310
        center_x = 500
        center_y = 500
        if drop_position is not None:
            card = self.box_preview._canvas_rect().adjusted(8, 8, -8, -8)
            if not card.isEmpty():
                center_x = round(
                    (drop_position.x() - card.x()) * 1000 / card.width()
                )
                center_y = round(
                    (drop_position.y() - card.y()) * 1000 / card.height()
                )
        style.update(
            {
                "overlay_x": str(max(0, min(1000 - width, center_x - width // 2))),
                "overlay_y": str(max(0, min(1000 - height, center_y - height // 2))),
                "overlay_width": str(width),
                "overlay_height": str(height),
            }
        )
        self.field_styles[new_id] = style

        list_item = QListWidgetItem(self._field_list_text(new_field))
        list_item.setData(Qt.ItemDataRole.UserRole, new_id)
        list_item.setData(Qt.ItemDataRole.UserRole + 1, field_type)
        list_item.setData(Qt.ItemDataRole.UserRole + 2, "")
        list_item.setToolTip(
            "Drag to reorder, or drop onto an image to make an overlay"
        )
        insert_row = self._default_insert_index(
            [
                {
                    "id": str(
                        self.field_order_list.item(index).data(
                            Qt.ItemDataRole.UserRole
                        )
                        or ""
                    ),
                    "type": str(
                        self.field_order_list.item(index).data(
                            Qt.ItemDataRole.UserRole + 1
                        )
                        or ""
                    ),
                }
                for index in range(self.field_order_list.count())
            ],
            source_id,
            item_kind,
        )
        self.field_order_list.insertItem(insert_row, list_item)
        self.field_order_list.setCurrentItem(list_item)
        self._field_order_changed()
        return new_id

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

        list_item = QListWidgetItem(self._field_list_text(duplicate))
        list_item.setData(Qt.ItemDataRole.UserRole, new_id)
        list_item.setData(Qt.ItemDataRole.UserRole + 1, field_type)
        list_item.setData(
            Qt.ItemDataRole.UserRole + 2,
            self.field_styles[new_id].get("parent_id", ""),
        )
        list_item.setToolTip(
            "Drop onto an image to overlay it; drop between rows to detach"
        )
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

    def _sync_order_item_hierarchy(self) -> None:
        parent_ids = {
            str(style.get("parent_id", ""))
            for style in self.field_styles.values()
            if style.get("parent_id")
        }
        for index in range(self.field_order_list.count()):
            item = self.field_order_list.item(index)
            field_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                self.field_types.get(field_id, "text"),
            )
            item.setData(
                Qt.ItemDataRole.UserRole + 2,
                self.field_styles.get(field_id, {}).get("parent_id", ""),
            )
            item.setData(Qt.ItemDataRole.UserRole + 3, field_id in parent_ids)

    def _rebuild_order_list(self, ordered_ids: list[str], selected_id: str) -> None:
        fields = self._image_item.display_fields()
        by_id = {str(field.get("id", "")): field for field in fields}
        ordered_fields = [by_id[field_id] for field_id in ordered_ids if field_id in by_id]
        ordered_fields.extend(
            field for field in fields if str(field.get("id", "")) not in ordered_ids
        )
        self._image_item.set_fields(ordered_fields)
        self.field_order_list.clear()
        for field in ordered_fields:
            field_id = str(field.get("id", ""))
            field_type = str(field.get("type", "text"))
            item = QListWidgetItem(self._field_list_text(field))
            item.setData(Qt.ItemDataRole.UserRole, field_id)
            item.setData(Qt.ItemDataRole.UserRole + 1, field_type)
            item.setData(
                Qt.ItemDataRole.UserRole + 2,
                self.field_styles.get(field_id, {}).get("parent_id", ""),
            )
            item.setToolTip(
                "Drop onto an image to overlay it; drop between rows to detach"
            )
            self.field_order_list.addItem(item)
            if field_id == selected_id:
                self.field_order_list.setCurrentItem(item)
        self._sync_order_item_hierarchy()

    def _hierarchy_drop_requested(
        self,
        source_id: str,
        target_id: str,
        drop_after: bool,
        parent_id: str,
    ) -> None:
        if source_id not in self.field_types:
            return
        order = self._ordered_field_ids()
        if source_id not in order:
            return
        source_type = self.field_types.get(source_id, "text")
        if source_type == "image":
            parent_id = ""
            moving = [source_id] + [
                field_id
                for field_id in order
                if self.field_styles.get(field_id, {}).get("parent_id") == source_id
            ]
        else:
            moving = [source_id]
        remaining = [field_id for field_id in order if field_id not in moving]
        if parent_id and self.field_types.get(parent_id) != "image":
            parent_id = ""
        self.field_styles.setdefault(source_id, {})["parent_id"] = parent_id

        if not target_id or target_id not in remaining:
            insert_at = len(remaining)
        elif parent_id and target_id == parent_id:
            insert_at = remaining.index(parent_id) + 1
            while (
                insert_at < len(remaining)
                and self.field_styles.get(remaining[insert_at], {}).get("parent_id")
                == parent_id
            ):
                insert_at += 1
        else:
            insert_at = remaining.index(target_id) + int(drop_after)
            if not parent_id and drop_after and self.field_types.get(target_id) == "image":
                while (
                    insert_at < len(remaining)
                    and self.field_styles.get(remaining[insert_at], {}).get("parent_id")
                    == target_id
                ):
                    insert_at += 1
        new_order = remaining[:insert_at] + moving + remaining[insert_at:]
        self._rebuild_order_list(new_order, source_id)
        self._update_preview()

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
            if template is None:
                continue
            duplicate = dict(source) if source is not None else dict(template)
            duplicate["id"] = new_id
            duplicate["label"] = str(
                template.get("label")
                or (source.get("label") if source is not None else "")
                or "Input"
            )
            duplicate["type"] = str(
                template.get("type")
                or (source.get("type") if source is not None else "")
                or "text"
            )
            duplicate["role"] = str(
                template.get("role")
                or (source.get("role") if source is not None else "")
                or ""
            )
            result.append(duplicate)
        return result

    def _field_order_changed(self, *_args) -> None:
        self._image_item.set_fields(self._ordered_fields(self._image_item.display_fields()))
        self._update_preview()

    def _preview_field_reorder_requested(
        self, source_id: str, target_id: str, drop_after: bool
    ) -> None:
        if source_id == target_id:
            return
        target_parent = self.field_styles.get(target_id, {}).get("parent_id", "")
        parent_id = ""
        if self.field_types.get(source_id) != "image":
            if self.field_types.get(target_id) == "image":
                parent_id = target_id
            elif target_parent:
                parent_id = target_parent
        self._hierarchy_drop_requested(
            source_id, target_id, drop_after, parent_id
        )

    def _preview_layer_order_requested(
        self, field_id: str, operation: str
    ) -> None:
        order = self._ordered_field_ids()
        if field_id not in order:
            return

        field_types = {
            str(field.get("id", "")): str(field.get("type", "text"))
            for field in self._image_item.display_fields()
        }

        def parent_for(candidate_id: str) -> str:
            if field_types.get(candidate_id) == "image":
                return ""
            parent_id = str(
                self.field_styles.get(candidate_id, {}).get("parent_id", "")
            )
            return parent_id if field_types.get(parent_id) == "image" else ""

        parent_id = parent_for(field_id)
        siblings = [
            candidate_id
            for candidate_id in order
            if parent_for(candidate_id) == parent_id
        ]
        try:
            sibling_index = siblings.index(field_id)
        except ValueError:
            return

        if operation == "bring_to_front":
            target_index = len(siblings) - 1
        elif operation == "bring_forward":
            target_index = min(len(siblings) - 1, sibling_index + 1)
        elif operation == "send_backward":
            target_index = max(0, sibling_index - 1)
        elif operation == "send_to_back":
            target_index = 0
        else:
            return
        if target_index == sibling_index:
            return

        target_id = siblings[target_index]
        updated_order = list(order)
        if operation in {"bring_forward", "send_backward"}:
            source_position = updated_order.index(field_id)
            target_position = updated_order.index(target_id)
            updated_order[source_position], updated_order[target_position] = (
                updated_order[target_position],
                updated_order[source_position],
            )
        else:
            updated_order.remove(field_id)
            target_position = updated_order.index(target_id)
            insert_at = target_position + int(operation == "bring_to_front")
            updated_order.insert(insert_at, field_id)

        self._rebuild_order_list(updated_order, field_id)
        self._update_preview()

    def _preview_field_selected(self, field_id: str) -> None:
        for index in range(self.field_order_list.count()):
            item = self.field_order_list.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole) or "") == field_id:
                if self.field_order_list.currentItem() is item:
                    self._load_selected_field_style()
                else:
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
        self._undo_stack: list[tuple[dict, str]] = []
        self._redo_stack: list[tuple[dict, str]] = []
        self._restoring_history = False
        self._audio_source_paths: tuple[str, ...] = ()
        self._audio_players: list[QMediaPlayer] = []
        self._audio_outputs: list[QAudioOutput] = []
        self._elapsed = QElapsedTimer()
        self._last_elapsed_ms = 0
        self.preferences = QSettings("DataCompareTools", "DataComparisonVideoMaker")
        self._audio_device_key = str(
            self.preferences.value("audio_output_device", "") or ""
        )
        self._media_devices = QMediaDevices(self)
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

        self._media_devices.audioOutputsChanged.connect(self._refresh_audio_outputs)
        self._refresh_audio_outputs()
        self._refresh_all()

    def _build_ui(self) -> None:
        command_bar = QWidget()
        command_bar.setObjectName("EditorToolbar")
        command_layout = QHBoxLayout(command_bar)
        command_layout.setContentsMargins(14, 9, 14, 9)
        command_layout.setSpacing(8)
        app_title = QLabel("Data Compare")
        app_title.setObjectName("AppTitle")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(self.theme.title())
        self.theme_combo.setMinimumWidth(90)
        self.toolbar_export_button = QPushButton("Export")
        self.toolbar_export_button.setObjectName("PrimaryButton")
        command_layout.addWidget(app_title)
        command_layout.addStretch(1)
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
        self.undo_action = self._add_action(
            edit_menu, "Undo", self.undo, QKeySequence.StandardKey.Undo
        )
        self.redo_action = self._add_action(
            edit_menu, "Redo", self.redo, QKeySequence.StandardKey.Redo
        )
        self._update_history_actions()
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
        self.transport.box_duration_changed.connect(self.set_box_duration)
        self.transport.audio_output_changed.connect(self.set_audio_output_device)
        self.transport.customize_requested.connect(self.open_box_customization)
        self.transport.screenshot_requested.connect(self.save_screenshot)
        self.transport.background_requested.connect(self.open_canvas_background)
        self.toolbar_export_button.clicked.connect(self.export_video)
        self.theme_combo.currentTextChanged.connect(self.set_theme)

    def _add_action(self, menu, text: str, slot, shortcut=None) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _history_snapshot(self) -> dict:
        return {
            "project": deepcopy(self.project.to_dict()),
            "selected_item_id": self.selected_item_id,
            "current_time": self.current_time,
        }

    def _record_project_change(self, before: dict, label: str) -> None:
        if self._restoring_history or before["project"] == self.project.to_dict():
            return
        self._undo_stack.append((before, label))
        del self._undo_stack[:-100]
        self._redo_stack.clear()
        self._update_history_actions()

    def _restore_history_snapshot(self, snapshot: dict) -> None:
        self._restoring_history = True
        try:
            self.pause_playback()
            self.project = Project.from_dict(deepcopy(snapshot["project"]))
            selected_id = str(snapshot.get("selected_item_id", ""))
            self.selected_item_id = (
                selected_id
                if self.project.item_by_id(selected_id) is not None
                else (
                    self.project.comparison_items[0].id
                    if self.project.comparison_items
                    else ""
                )
            )
            self.current_time = clamp(
                float(snapshot.get("current_time", 0.0)),
                0.0,
                self.project.total_duration(),
            )
            self._refresh_all()
        finally:
            self._restoring_history = False

    def _update_history_actions(self) -> None:
        if not hasattr(self, "undo_action"):
            return
        undo_label = self._undo_stack[-1][1] if self._undo_stack else ""
        redo_label = self._redo_stack[-1][1] if self._redo_stack else ""
        self.undo_action.setText(f"Undo {undo_label}" if undo_label else "Undo")
        self.redo_action.setText(f"Redo {redo_label}" if redo_label else "Redo")
        self.undo_action.setEnabled(bool(self._undo_stack))
        self.redo_action.setEnabled(bool(self._redo_stack))

    def _clear_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_history_actions()

    def undo(self) -> None:
        if not self._undo_stack:
            return
        snapshot, label = self._undo_stack.pop()
        self._redo_stack.append((self._history_snapshot(), label))
        self._restore_history_snapshot(snapshot)
        self._update_history_actions()
        self.statusBar().showMessage(f"Undid {label.lower()}", 2500)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        snapshot, label = self._redo_stack.pop()
        self._undo_stack.append((self._history_snapshot(), label))
        self._restore_history_snapshot(snapshot)
        self._update_history_actions()
        self.statusBar().showMessage(f"Redid {label.lower()}", 2500)

    def _refresh_all(self) -> None:
        self.project.apply_fixed_item_timing()
        self._normalize_field_schema()
        self._normalize_box_design()
        self.preview.set_project(self.project)
        self.timeline.set_project(self.project)
        self.assets.set_items(self.project.comparison_items, self.selected_item_id)
        self.transport.set_columns(self.project.preview_max_columns)
        self.transport.set_opening_animation(self.project.opening_animation)
        self.transport.set_box_duration(self.project.item_fixed_duration)
        self._sync_audio_sources()
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

    def set_current_time(self, seconds: float, sync_audio: bool = True) -> None:
        self.current_time = clamp(seconds, 0.0, self.project.total_duration())
        self.preview.set_current_time(self.current_time)
        self.timeline.set_current_time(self.current_time)
        if sync_audio:
            self._seek_audio(self.current_time)
        self._update_status()

    def set_preview_columns(self, columns: int) -> None:
        before = self._history_snapshot()
        self.project.preview_max_columns = max(
            MIN_PREVIEW_COLUMNS_1080P,
            min(MAX_PREVIEW_COLUMNS_1080P, int(columns)),
        )
        self.transport.set_columns(self.project.preview_max_columns)
        self.preview.update()
        self._update_status()
        self._record_project_change(before, "preview columns")

    def set_opening_animation(self, animation: str) -> None:
        before = self._history_snapshot()
        if animation not in {value for _, value in OPENING_ANIMATION_OPTIONS}:
            animation = "slide_left"
        self.project.opening_animation = animation
        self.transport.set_opening_animation(animation)
        self.preview.update()
        self._record_project_change(before, "opening animation")

    def set_box_duration(self, duration: float) -> None:
        before = self._history_snapshot()
        self.project.item_fixed_duration = max(MIN_CLIP_DURATION, float(duration))
        self.project.apply_fixed_item_timing()
        self.transport.set_box_duration(self.project.item_fixed_duration)
        self.set_current_time(min(self.current_time, self.project.total_duration()))
        self.preview.update()
        self.timeline.set_project(self.project)
        self.timeline.set_selected_item(self.selected_item_id)
        self._update_status()
        self._record_project_change(before, "box duration")

    def add_comparison_item(self) -> None:
        before = self._history_snapshot()
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
        self._record_project_change(before, "add item")

    def add_text(self) -> None:
        template = (
            self.project.item_by_id(self.selected_item_id)
            or (self.project.comparison_items[0] if self.project.comparison_items else None)
            or ComparisonItem(name="Item", rank="#1", category="CATEGORY", value="Value")
        )
        schema = template.display_fields()
        preview = BoxStylePreview(
            template,
            self.project.height,
            self,
            self.project.width,
        )
        preview.resize(640, 1080)
        columns = self.project.preview_max_columns
        preview.set_style(
            template.image_fit or self.project.image_fit,
            getattr(template, f"image_height_percent_{columns}", 0)
            or getattr(self.project, f"image_height_percent_{columns}"),
            self.project.card_border_color,
            self.project.text_font_family,
            self.project.field_styles,
            self.project.text_font_size,
            columns,
            border_width=self.project.card_border_width,
        )
        import_schema = preview.fields_in_visual_order()
        preview.deleteLater()
        dialog = TextImportDialog(self, schema=import_schema)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = self._history_snapshot()
        imported = dialog.imported_items()
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
            fields = []
            for template_field in schema:
                field = dict(template_field)
                field_id = str(field["id"])
                if field.get("type") == "shape":
                    field["value"] = row.get(field_id) or field.get("value", "")
                else:
                    field["value"] = row.get(field_id, "")
                fields.append(field)
            item.set_fields(fields)
            item.name = row["name"]
            self.project.comparison_items.append(item)
            first_new_id = first_new_id or item.id
        self.project.apply_fixed_item_timing()
        self.selected_item_id = first_new_id
        self.current_time = 0.0
        self._refresh_all()
        self._record_project_change(before, "import text data")
        self.statusBar().showMessage(f"Imported {len(imported)} items", 3500)

    def open_canvas_background(self) -> None:
        self.pause_playback()
        dialog = CanvasBackgroundDialog(self.project, self.current_time, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = self._history_snapshot()
        dialog.apply_to(self.project)
        self.preview.set_project(self.project)
        self._record_project_change(before, "canvas background")
        self.statusBar().showMessage("Updated canvas background", 3500)

    def open_box_customization(self, item_id: str = "") -> None:
        item = self.project.item_by_id(item_id or self.selected_item_id)
        if item is None:
            self._warning("Select a comparison item to customize.")
            return
        dialog = BoxCustomizationDialog(self.project, item, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = self._history_snapshot()
        dialog.apply_changes()
        self._refresh_all()
        self._record_project_change(before, "box design")
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
        frame = image_field_frame_size(
            fields,
            field_id,
            self.project.field_styles,
            QSize(self.project.width // columns, self.project.height),
            percent,
        )
        dialog = ImageEditorDialog(
            str(field.get("value", "")), frame, item.image_fit or self.project.image_fit,
            item.image_transforms.get(field_id), self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        before = self._history_snapshot()
        field["value"] = dialog.image_path
        item.set_fields(fields)
        item.image_transforms[field_id] = dialog.image_transform()
        if dialog.apply_to_all_boxes:
            transform = dialog.image_transform()
            for existing_item in self.project.comparison_items:
                existing_fields = existing_item.display_fields()
                target_field = next(
                    (
                        field for field in existing_fields
                        if field.get("id") == field_id and field.get("type") == "image"
                    ),
                    None,
                )
                if target_field is not None:
                    target_field["value"] = dialog.image_path
                    existing_item.set_fields(existing_fields)
                    existing_item.image_transforms[field_id] = dict(transform)
        self._refresh_all()
        self._record_project_change(before, "image edit")
        message = (
            "Applied image and placement to all boxes"
            if dialog.apply_to_all_boxes else f"Updated image for {item.name}"
        )
        self.statusBar().showMessage(message, 3500)

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
        before = self._history_snapshot()
        item.set_image_path(path)
        self._refresh_all()
        self._record_project_change(before, "import image")

    def import_audio(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Audio",
            str(Path.home()),
            SUPPORTED_AUDIO_FILTER,
        )
        if not path:
            return
        audio_path = Path(path).resolve()
        if not audio_path.is_file() or audio_path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
            self._warning("The selected audio file could not be opened or is not supported.")
            return
        normalized = str(audio_path)
        if normalized in self.project.audio_paths:
            self.statusBar().showMessage(f"Audio already added: {audio_path.name}", 3500)
            return
        before = self._history_snapshot()
        self.project.audio_paths.append(normalized)
        self._sync_audio_sources()
        self.timeline.set_project(self.project)
        output_name = self._selected_audio_device_description()
        output_detail = f" | Output: {output_name}" if output_name else ""
        self.statusBar().showMessage(
            f"Imported audio: {audio_path.name}{output_detail}", 5000
        )
        self._record_project_change(before, "import audio")

    def update_item_properties(self, changes: dict) -> None:
        item = self.project.item_by_id(str(changes.get("id", "")))
        if item is None:
            return
        before = self._history_snapshot()
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
        self._record_project_change(before, "item properties")

    def update_item_fields(self, item_id: str, fields: list) -> None:
        item = self.project.item_by_id(item_id)
        if item is None:
            return
        before = self._history_snapshot()
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
        self._record_project_change(before, "item fields")

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
        before = self._history_snapshot()
        self.project.item_fixed_duration = max(MIN_CLIP_DURATION, float(duration))
        self.project.apply_fixed_item_timing()
        self.transport.set_box_duration(self.project.item_fixed_duration)
        self.preview.update()
        self.timeline.set_project(self.project)
        self._update_status()
        self._record_project_change(before, "item timing")

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
        before = self._history_snapshot()
        self.project.comparison_items = [
            existing for existing in self.project.comparison_items if existing.id != self.selected_item_id
        ]
        self.selected_item_id = self.project.comparison_items[0].id if self.project.comparison_items else ""
        self._refresh_all()
        self._record_project_change(before, "delete item")

    def duplicate_selected_item(self) -> None:
        item = self.project.item_by_id(self.selected_item_id)
        if item is None:
            self._warning("Select an item to duplicate.")
            return
        before = self._history_snapshot()
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
        self._record_project_change(before, "duplicate item")

    def new_project(self) -> None:
        if not self._confirm_discard():
            return
        project = Project.sample()
        dialog = ProjectSettingsDialog(project, self)
        dialog.setWindowTitle("Create Project")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        dialog.apply_to(project)
        self.project = project
        self.project_path = None
        self.selected_item_id = self.project.comparison_items[0].id if self.project.comparison_items else ""
        self.current_time = 0.0
        self._clear_history()
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
        self._clear_history()
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
            before = self._history_snapshot()
            dialog.apply_to(self.project)
            self.set_current_time(min(self.current_time, self.project.total_duration()))
            self._refresh_all()
            self._record_project_change(before, "project settings")

    def save_screenshot(self) -> None:
        self.pause_playback()
        frame_time = self.current_time
        directory = self.project_path.parent if self.project_path else Path.home()
        dialog = QFileDialog(self, "Save Screenshot", str(directory), "PNG image (*.png)")
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("png")
        dialog.selectFile(f"screenshot_{round(frame_time * 1000):06d}.png")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        options = ExportOptions(
            path=Path(dialog.selectedFiles()[0]),
            format_name="png",
            width=self.project.width,
            height=self.project.height,
            fps=self.project.fps,
            duration=self.project.total_duration(),
        )
        try:
            completed = export_preview(self.preview, options, frame_time)
        except (ExportError, OSError) as exc:
            self._warning(str(exc))
            return
        if completed:
            self.statusBar().showMessage(f"Screenshot saved: {options.path}", 5000)

    def export_video(self) -> None:
        dialog = ExportDialog(
            self.project.name,
            self.project.fps,
            self.project.total_duration(),
            self.project.content_duration(),
            self,
            project_width=self.project.width,
            project_height=self.project.height,
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
                self.preview,
                options,
                self.current_time,
                report_progress,
                audio_paths=self.project.audio_paths,
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
        self._seek_audio(self.current_time)
        for player in self._audio_players:
            player.play()
        self._elapsed.restart()
        self._last_elapsed_ms = 0
        self.playback_timer.start()

    def pause_playback(self) -> None:
        self.playing = False
        self.transport.set_playing(False)
        self.playback_timer.stop()
        for player in self._audio_players:
            player.pause()

    def stop_playback(self) -> None:
        self.pause_playback()
        self.set_current_time(0.0)

    @staticmethod
    def _audio_device_id(device) -> str:
        return bytes(device.id()).hex()

    def _available_audio_devices(self) -> list:
        return list(QMediaDevices.audioOutputs())

    def _choose_audio_device_id(self, devices: list) -> str:
        device_ids = {self._audio_device_id(device) for device in devices}
        if self._audio_device_key in device_ids:
            return self._audio_device_key
        if not devices:
            return ""

        default_device = QMediaDevices.defaultAudioOutput()
        default_id = (
            self._audio_device_id(default_device)
            if not default_device.isNull()
            else ""
        )
        default_description = default_device.description().lower()
        # Some Realtek drivers expose an unused alternate jack as the Windows
        # default. Prefer the physical Speakers endpoint on first use, while the
        # selector still lets the user choose headphones, a display, or digital out.
        if not self._audio_device_key and (
            "2nd output" in default_description or "digital output" in default_description
        ):
            speaker = next(
                (
                    device
                    for device in devices
                    if device.description().lower().startswith("speakers")
                ),
                None,
            )
            if speaker is not None:
                return self._audio_device_id(speaker)
        return default_id if default_id in device_ids else self._audio_device_id(devices[0])

    def _selected_audio_device(self):
        devices = self._available_audio_devices()
        selected_id = self._choose_audio_device_id(devices)
        return next(
            (
                device
                for device in devices
                if self._audio_device_id(device) == selected_id
            ),
            None,
        )

    def _selected_audio_device_description(self) -> str:
        device = self._selected_audio_device()
        return device.description() if device is not None else ""

    def _refresh_audio_outputs(self) -> None:
        devices = self._available_audio_devices()
        selected_id = self._choose_audio_device_id(devices)
        device_changed = selected_id != self._audio_device_key
        self._audio_device_key = selected_id
        self.transport.set_audio_outputs(
            [
                (self._audio_device_id(device), device.description())
                for device in devices
            ],
            selected_id,
        )
        if device_changed and self._audio_source_paths:
            self._sync_audio_sources(force=True)

    def set_audio_output_device(self, device_id: str) -> None:
        if not device_id or device_id == self._audio_device_key:
            return
        devices = self._available_audio_devices()
        device = next(
            (
                candidate
                for candidate in devices
                if self._audio_device_id(candidate) == device_id
            ),
            None,
        )
        if device is None:
            self._refresh_audio_outputs()
            return
        self._audio_device_key = device_id
        self.preferences.setValue("audio_output_device", device_id)
        self._sync_audio_sources(force=True)
        self.statusBar().showMessage(
            f"Audio output: {device.description()}", 5000
        )

    def _sync_audio_sources(self, force: bool = False) -> None:
        paths = tuple(
            str(Path(path).resolve())
            for path in self.project.audio_paths
            if Path(path).is_file()
            and Path(path).suffix.lower() in SUPPORTED_AUDIO_SUFFIXES
        )
        if paths == self._audio_source_paths and not force:
            return
        for player in self._audio_players:
            player.stop()
            player.deleteLater()
        for output in self._audio_outputs:
            output.deleteLater()
        self._audio_players = []
        self._audio_outputs = []
        self._audio_source_paths = paths
        device = self._selected_audio_device()
        for path in paths:
            output = QAudioOutput(device, self) if device is not None else QAudioOutput(self)
            output.setMuted(False)
            output.setVolume(1.0 / max(1, len(paths)))
            player = QMediaPlayer(self)
            player.setAudioOutput(output)
            player.mediaStatusChanged.connect(
                lambda status, source=player: self._audio_status_changed(source, status)
            )
            player.errorOccurred.connect(
                lambda _error, message, source_path=path: self._audio_error(
                    source_path, message
                )
            )
            player.setSource(QUrl.fromLocalFile(path))
            self._audio_outputs.append(output)
            self._audio_players.append(player)
        self._seek_audio(self.current_time)

    def _audio_status_changed(
        self,
        player: QMediaPlayer,
        status: QMediaPlayer.MediaStatus,
    ) -> None:
        if status not in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            return
        player.setPosition(round(self.current_time * 1000))
        if self.playing:
            player.play()

    def _seek_audio(self, seconds: float) -> None:
        position = max(0, round(seconds * 1000))
        for player in self._audio_players:
            player.setPosition(position)

    def _audio_error(self, path: str, message: str) -> None:
        detail = message.strip() or "the audio decoder rejected this file"
        self.statusBar().showMessage(
            f"Could not play {Path(path).name}: {detail}",
            7000,
        )

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
        self.set_current_time(next_time, sync_audio=False)

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
            colors = LIGHT_COLORS if normalized == "light" else DARK_COLORS
            palette = QPalette()
            for role, token in (
                (QPalette.ColorRole.Window, "@base"),
                (QPalette.ColorRole.Base, "@base"),
                (QPalette.ColorRole.AlternateBase, "@popup"),
                (QPalette.ColorRole.Button, "@base"),
                (QPalette.ColorRole.WindowText, "@text"),
                (QPalette.ColorRole.Text, "@text"),
                (QPalette.ColorRole.ButtonText, "@text"),
                (QPalette.ColorRole.PlaceholderText, "@textMuted"),
                (QPalette.ColorRole.Mid, "@textDisabled"),
                (QPalette.ColorRole.Highlight, "@accent"),
                (QPalette.ColorRole.Link, "@selectedText"),
                (QPalette.ColorRole.ToolTipBase, "@popup"),
                (QPalette.ColorRole.ToolTipText, "@text"),
            ):
                palette.setColor(role, QColor(colors[token]))
            palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            for role in (
                QPalette.ColorRole.WindowText,
                QPalette.ColorRole.Text,
                QPalette.ColorRole.ButtonText,
            ):
                palette.setColor(
                    QPalette.ColorGroup.Disabled, role, QColor(colors["@textDisabled"])
                )
            application.setPalette(palette)
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
