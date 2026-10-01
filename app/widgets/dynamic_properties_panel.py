from __future__ import annotations

from functools import partial
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QEvent, QMimeData, QPoint, QSize, Signal, Qt
from PySide6.QtGui import (
    QColor,
    QDrag,
    QIcon,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.comparison_item import ComparisonItem
from app.settings import MIN_CLIP_DURATION, SUPPORTED_IMAGE_FILTER


FIELD_TYPES = (
    ("Name", "name"),
    ("Text", "text"),
    ("Number", "number"),
    ("Image", "image"),
)

FIELD_ROW_MIME_TYPE = "application/x-data-compare-input-field"


def _tinted_standard_icon(widget: QWidget, pixmap: QStyle.StandardPixmap) -> QIcon:
    icon_pixmap = widget.style().standardIcon(pixmap).pixmap(18, 18)
    painter = QPainter(icon_pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(icon_pixmap.rect(), QColor("#dc2626"))
    painter.end()
    return QIcon(icon_pixmap)


def _plus_icon() -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#ffffff"), 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(4, 9, 14, 9)
    painter.drawLine(9, 4, 9, 14)
    painter.end()
    return QIcon(pixmap)


class DragHandle(QWidget):
    drag_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._press_position: QPoint | None = None
        self.setFixedSize(24, 34)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip("Drag to reorder this input")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._press_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press_position).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._press_position = None
            self.drag_requested.emit()
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._press_position = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self.palette().color(QPalette.ColorRole.PlaceholderText)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        for x in (9, 15):
            for y in (11, 17, 23):
                painter.drawEllipse(QPoint(x, y), 1, 1)
        painter.end()


class InputFieldRow(QWidget):
    changed = Signal()
    remove_requested = Signal(object)
    drop_requested = Signal(str, object, bool)

    def __init__(self, field_data: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._id = field_data.get("id") or f"field_{uuid4().hex[:8]}"
        self._role = field_data.get("role", "")
        self._field_type = field_data.get("type", "text")
        self._drop_after: bool | None = None
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Label")
        type_names = {field_type: label for label, field_type in FIELD_TYPES}
        type_name = type_names.get(self._field_type, "Text")
        self.label_edit.setToolTip(f"{type_name} input label")
        self.value_edit = QLineEdit()
        self.browse_button = QPushButton("Upload")
        self.browse_button.setFixedWidth(72)
        self.drag_handle = DragHandle()
        self.drag_handle.drag_requested.connect(self._start_drag)
        self.remove_button = QToolButton()
        self.remove_button.setObjectName("DangerIconButton")
        self.remove_button.setIcon(
            _tinted_standard_icon(self.remove_button, QStyle.StandardPixmap.SP_TrashIcon)
        )
        self.remove_button.setIconSize(QSize(18, 18))
        self.remove_button.setToolTip("Remove this input from all boxes")
        self.remove_button.setFixedSize(34, 34)
        top_row.addWidget(self.drag_handle)
        top_row.addWidget(self.label_edit, 1)
        top_row.addWidget(self.remove_button)
        value_row.addWidget(self.value_edit, 1)
        value_row.addWidget(self.browse_button)
        layout.addLayout(top_row)
        layout.addLayout(value_row)

        self.label_edit.setText(field_data.get("label", ""))
        self.value_edit.setText(field_data.get("value", ""))
        self._update_type_ui()
        self.label_edit.textEdited.connect(lambda _text: self.changed.emit())
        self.value_edit.textEdited.connect(lambda _text: self.changed.emit())
        self.browse_button.clicked.connect(self._upload_image)
        self.remove_button.clicked.connect(lambda: self.remove_requested.emit(self))
        for child in (
            self.label_edit,
            self.value_edit,
            self.browse_button,
            self.remove_button,
            self.drag_handle,
        ):
            child.setAcceptDrops(True)
            child.installEventFilter(self)

    def field_data(self) -> dict[str, str]:
        field_type = self._field_type
        role = self._role
        if field_type == "name":
            role = "name"
        elif field_type == "image":
            role = "image"
        return {
            "id": self._id,
            "type": field_type,
            "label": self.label_edit.text().strip() or field_type.title(),
            "value": self.value_edit.text().strip(),
            "role": role,
        }

    def set_value(self, value: str) -> None:
        self.value_edit.setText(value)
        self.changed.emit()

    def _update_type_ui(self) -> None:
        is_image = self._field_type == "image"
        self.browse_button.setVisible(is_image)
        self.value_edit.setReadOnly(is_image)
        self.value_edit.setPlaceholderText("Choose an image" if is_image else "Enter value")

    def _upload_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload Image", str(Path.home()), SUPPORTED_IMAGE_FILTER
        )
        if path:
            self.set_value(path)

    def _start_drag(self) -> None:
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setData(FIELD_ROW_MIME_TYPE, self._id.encode("utf-8"))
        drag.setMimeData(mime_data)
        pixmap = self.grab()
        if pixmap.width() > 280:
            pixmap = pixmap.scaledToWidth(
                280, Qt.TransformationMode.SmoothTransformation
            )
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(12, 17))
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event) -> None:
        source_id = self._drag_source_id(event)
        if source_id and source_id != self._id:
            event.acceptProposedAction()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        source_id = self._drag_source_id(event)
        if not source_id or source_id == self._id:
            event.ignore()
            return
        self._drop_after = event.position().y() >= self.height() / 2
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._clear_drop_indicator()
        event.accept()

    def dropEvent(self, event) -> None:
        source_id = self._drag_source_id(event)
        if not source_id or source_id == self._id:
            self._clear_drop_indicator()
            event.ignore()
            return
        drop_after = event.position().y() >= self.height() / 2
        self._clear_drop_indicator()
        self.drop_requested.emit(source_id, self, drop_after)
        event.acceptProposedAction()

    def eventFilter(self, watched, event) -> bool:
        event_type = event.type()
        if event_type == QEvent.Type.DragLeave:
            self.dragLeaveEvent(event)
            return event.isAccepted()
        if not self._drag_source_id(event):
            return super().eventFilter(watched, event)
        if event_type == QEvent.Type.DragEnter:
            self.dragEnterEvent(event)
            return event.isAccepted()
        if event_type == QEvent.Type.DragMove:
            self._handle_drag_move(event, watched)
            return event.isAccepted()
        if event_type == QEvent.Type.Drop:
            self._handle_drop(event, watched)
            return event.isAccepted()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_after is None:
            return
        painter = QPainter(self)
        painter.setPen(
            QPen(self.palette().color(QPalette.ColorRole.Highlight), 3)
        )
        y = self.height() - 2 if self._drop_after else 1
        painter.drawLine(0, y, self.width(), y)
        painter.end()

    def _drag_source_id(self, event) -> str:
        if not hasattr(event, "mimeData"):
            return ""
        mime_data = event.mimeData()
        if not mime_data.hasFormat(FIELD_ROW_MIME_TYPE):
            return ""
        return bytes(mime_data.data(FIELD_ROW_MIME_TYPE)).decode("utf-8")

    def _clear_drop_indicator(self) -> None:
        self._drop_after = None
        self.update()

    def _event_y(self, event, watched: QWidget) -> int:
        if watched is self:
            return int(event.position().y())
        position = watched.mapTo(self, event.position().toPoint())
        return position.y()

    def _handle_drag_move(self, event, watched: QWidget) -> None:
        source_id = self._drag_source_id(event)
        if not source_id or source_id == self._id:
            event.ignore()
            return
        self._drop_after = self._event_y(event, watched) >= self.height() / 2
        self.update()
        event.acceptProposedAction()

    def _handle_drop(self, event, watched: QWidget) -> None:
        source_id = self._drag_source_id(event)
        if not source_id or source_id == self._id:
            self._clear_drop_indicator()
            event.ignore()
            return
        drop_after = self._event_y(event, watched) >= self.height() / 2
        self._clear_drop_indicator()
        self.drop_requested.emit(source_id, self, drop_after)
        event.acceptProposedAction()


class PropertiesPanel(QWidget):
    item_changed = Signal(dict)
    fields_changed = Signal(str, list)
    browse_image_requested = Signal()
    customize_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._current_id = ""
        self._field_rows: list[InputFieldRow] = []
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        title = QLabel("PROPERTIES")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        self.empty_label = QLabel("Select an item or clip to edit its properties.")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.form_widget = QWidget()
        self.form_widget.setObjectName("PropertiesContent")
        content_layout = QVBoxLayout(self.form_widget)
        content_layout.setContentsMargins(6, 6, 8, 10)
        content_layout.setSpacing(14)

        fields_header = QHBoxLayout()
        fields_header.setContentsMargins(0, 0, 0, 2)
        fields_header.setSpacing(8)
        fields_title = QLabel("INPUTS - ALL BOXES")
        fields_title.setObjectName("PanelTitle")
        self.add_field_button = QToolButton()
        self.add_field_button.setObjectName("AddIconButton")
        self.add_field_button.setIcon(_plus_icon())
        self.add_field_button.setIconSize(QSize(18, 18))
        self.add_field_button.setToolTip("Add an input to all boxes")
        self.add_field_button.setFixedSize(38, 38)
        self.add_field_menu = QMenu(self.add_field_button)
        for label, field_type in FIELD_TYPES:
            action = self.add_field_menu.addAction(label)
            action.triggered.connect(partial(self._add_field, field_type))
        self.add_field_button.clicked.connect(self._show_add_field_menu)
        fields_header.addWidget(fields_title)
        fields_header.addStretch(1)
        fields_header.addWidget(self.add_field_button)
        content_layout.addLayout(fields_header)

        self.fields_widget = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_widget)
        self.fields_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_layout.setSpacing(10)
        content_layout.addWidget(self.fields_widget)
        self.customize_button = QPushButton("Customize All Boxes")
        self.customize_button.setObjectName("PrimaryButton")
        content_layout.addWidget(self.customize_button)

        timing_title = QLabel("BOX TIMING - ALL BOXES")
        timing_title.setObjectName("PanelTitle")
        content_layout.addWidget(timing_title)
        timing_form = QFormLayout()
        timing_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        timing_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(MIN_CLIP_DURATION, 24 * 60 * 60)
        self.duration_spin.setDecimals(3)
        self.duration_spin.setSingleStep(0.1)
        self.duration_spin.setMaximumWidth(140)
        timing_form.addRow("Duration per box", self.duration_spin)
        content_layout.addLayout(timing_form)
        content_layout.addStretch(1)
        self.scroll.setWidget(self.form_widget)
        layout.addWidget(self.scroll, 1)

        self.customize_button.clicked.connect(
            lambda: self.customize_requested.emit(self._current_id)
        )
        self.duration_spin.valueChanged.connect(
            lambda value: self._emit_change("duration", value)
        )
        self.set_item(None)

    def set_item(self, item: ComparisonItem | None) -> None:
        self._current_id = item.id if item else ""
        self.empty_label.setVisible(item is None)
        self.scroll.setVisible(item is not None)
        self._updating = True
        self._clear_fields()
        self.duration_spin.blockSignals(True)
        if item is not None:
            for field_data in item.display_fields():
                self._append_field_row(field_data)
            self.duration_spin.setValue(item.duration)
        self.duration_spin.blockSignals(False)
        self._updating = False

    def set_image_path(self, path: str) -> None:
        for row in self._field_rows:
            if row.field_data()["type"] == "image":
                row.set_value(path)
                return
        self._add_field("image", value=path)

    def _show_add_field_menu(self) -> None:
        menu_position = self.add_field_button.mapToGlobal(
            QPoint(0, self.add_field_button.height() + 4)
        )
        self.add_field_menu.popup(menu_position)

    def _add_field(self, field_type: str, checked: bool = False, value: str = "") -> None:
        labels = {"name": "Name", "text": "Text", "number": "Number", "image": "Image"}
        field_data = {
            "id": f"field_{uuid4().hex[:8]}",
            "type": field_type,
            "label": labels[field_type],
            "value": value,
            "role": field_type if field_type in {"name", "image"} else "",
        }
        self._append_field_row(field_data)
        self._emit_fields()

    def _append_field_row(self, field_data: dict[str, str]) -> None:
        row = InputFieldRow(field_data)
        row.changed.connect(self._emit_fields)
        row.remove_requested.connect(self._remove_field)
        row.drop_requested.connect(self._drop_field)
        self._field_rows.append(row)
        self.fields_layout.addWidget(row)

    def _remove_field(self, row: InputFieldRow) -> None:
        if len(self._field_rows) <= 1:
            return
        self._field_rows.remove(row)
        self.fields_layout.removeWidget(row)
        row.deleteLater()
        self._emit_fields()

    def _drop_field(
        self, source_id: str, target_row: InputFieldRow, drop_after: bool
    ) -> None:
        source_row = next(
            (row for row in self._field_rows if row.field_data()["id"] == source_id),
            None,
        )
        if source_row is None or source_row is target_row:
            return
        source_index = self._field_rows.index(source_row)
        target_index = self._field_rows.index(target_row) + int(drop_after)
        self._field_rows.pop(source_index)
        if source_index < target_index:
            target_index -= 1
        self._field_rows.insert(target_index, source_row)
        self.fields_layout.removeWidget(source_row)
        self.fields_layout.insertWidget(target_index, source_row)
        self._emit_fields()

    def _clear_fields(self) -> None:
        for row in self._field_rows:
            self.fields_layout.removeWidget(row)
            row.deleteLater()
        self._field_rows.clear()

    def _emit_fields(self) -> None:
        if self._current_id and not self._updating:
            self.fields_changed.emit(
                self._current_id, [row.field_data() for row in self._field_rows]
            )

    def _emit_change(self, key: str, value: object) -> None:
        if self._current_id and not self._updating:
            self.item_changed.emit({"id": self._current_id, key: value})
