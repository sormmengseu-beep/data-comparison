from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Signal, Qt
from PySide6.QtGui import QPainter, QPainterPath
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.models.comparison_item import ComparisonItem
from app.utils.icons import IconButton, make_icon
from app.utils.image_utils import ImageCache


class ElidedLabel(QLabel):
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        painter.end()


class ItemThumbnail(QLabel):
    def __init__(self, item: ComparisonItem, cache: ImageCache) -> None:
        super().__init__()
        self.setObjectName("ItemThumbnail")
        self.setFixedSize(44, 44)
        self._pixmap = (
            cache.pixmap(item.image_path, QSize(40, 40), fit="cover")
            if item.image_path and Path(item.image_path).is_file() else None
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        target = QRectF(self.rect().adjusted(2, 2, -2, -2))
        clip = QPainterPath()
        clip.addRoundedRect(target, 6, 6)
        painter.setClipPath(clip)
        if self._pixmap is not None:
            painter.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        else:
            pixmap = make_icon("image", self.palette().color(self.foregroundRole())).pixmap(24, 24)
            painter.drawPixmap(10, 10, pixmap)
        painter.end()


class ComparisonItemRow(QWidget):
    edit_requested = Signal(str)

    def __init__(self, item: ComparisonItem, cache: ImageCache, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ComparisonItemRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setProperty("selected", False)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(12)
        thumbnail = ItemThumbnail(item, cache)
        layout.addWidget(thumbnail)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        name = ElidedLabel(item.name)
        name.setObjectName("ComparisonItemName")
        name.setToolTip(item.name)
        details = ElidedLabel(" · ".join(value for value in (item.rank, item.value) if value))
        details.setObjectName("ComparisonItemDetails")
        for label in (name, details):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            text_layout.addWidget(label)
        layout.addLayout(text_layout, 1)
        self.edit_button = IconButton("edit", f"Edit {item.name}")
        self.edit_button.setObjectName("ItemEditButton")
        self.edit_button.setFixedSize(32, 32)
        self.edit_button.clicked.connect(lambda: self.edit_requested.emit(item.id))
        layout.addWidget(self.edit_button)

    def set_selected(self, selected: bool) -> None:
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        for widget in (self, *self.findChildren(QWidget)):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.edit_button._refresh_icon()


class AssetPanel(QWidget):
    add_item_requested = Signal()
    upload_image_requested = Signal()
    add_text_requested = Signal()
    add_audio_requested = Signal()
    item_selected = Signal(str)
    customize_item_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self._image_cache = ImageCache()
        self._item_rows: dict[str, ComparisonItemRow] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("ASSETS")
        title.setObjectName("PanelTitle")
        self.count_label = QLabel("0 items")
        self.count_label.setObjectName("ItemCount")
        header = QHBoxLayout()
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.count_label)
        layout.addLayout(header)

        action_grid = QGridLayout()
        action_grid.setSpacing(6)
        self.add_item_button = QPushButton("New Item")
        self.add_item_button.setObjectName("PrimaryButton")
        self.upload_image_button = QPushButton("Set Image")
        self.add_text_button = QPushButton("Import Text")
        self.add_audio_button = QPushButton("Add Audio")
        action_grid.addWidget(self.add_item_button, 0, 0)
        action_grid.addWidget(self.add_text_button, 0, 1)
        action_grid.addWidget(self.upload_image_button, 1, 0)
        action_grid.addWidget(self.add_audio_button, 1, 1)
        layout.addLayout(action_grid)

        section = QLabel("Comparison Items")
        section.setObjectName("PanelTitle")
        layout.addSpacing(8)
        layout.addWidget(section)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search items")
        self.search_edit.setClearButtonEnabled(True)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName("ComparisonItemList")
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        layout.addWidget(self.list_widget, 1)

        self.add_item_button.clicked.connect(self.add_item_requested.emit)
        self.upload_image_button.clicked.connect(self.upload_image_requested.emit)
        self.add_text_button.clicked.connect(self.add_text_requested.emit)
        self.add_audio_button.clicked.connect(self.add_audio_requested.emit)
        self.list_widget.currentItemChanged.connect(self._current_item_changed)
        self.list_widget.itemDoubleClicked.connect(
            lambda item: self.customize_item_requested.emit(str(item.data(256)))
        )
        self.search_edit.textChanged.connect(self._filter_items)

    def set_items(self, items: list[ComparisonItem], selected_id: str = "") -> None:
        self.count_label.setText(f"{len(items)} item{'s' if len(items) != 1 else ''}")
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        self._item_rows.clear()
        for item in items:
            list_item = QListWidgetItem(f"{item.name}\n{item.rank}  {item.value}".strip())
            list_item.setData(256, item.id)
            self.list_widget.addItem(list_item)
            row = ComparisonItemRow(item, self._image_cache)
            row.edit_requested.connect(self._edit_item)
            list_item.setSizeHint(QSize(0, 68))
            self.list_widget.setItemWidget(list_item, row)
            self._item_rows[item.id] = row
            if item.id == selected_id:
                self.list_widget.setCurrentItem(list_item)
        self.list_widget.blockSignals(False)
        self._sync_row_selection()
        self._filter_items(self.search_edit.text())

    def select_item(self, item_id: str) -> None:
        self.list_widget.blockSignals(True)
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.data(256) == item_id:
                self.list_widget.setCurrentItem(item)
                break
        self.list_widget.blockSignals(False)
        self._sync_row_selection()

    def _sync_row_selection(self) -> None:
        current = self.list_widget.currentItem()
        selected_id = str(current.data(256)) if current is not None else ""
        for item_id, row in self._item_rows.items():
            row.set_selected(item_id == selected_id)

    def _edit_item(self, item_id: str) -> None:
        self.select_item(item_id)
        self.item_selected.emit(item_id)
        self.customize_item_requested.emit(item_id)

    def _current_item_changed(self, current: QListWidgetItem | None) -> None:
        self._sync_row_selection()
        if current is not None:
            self.item_selected.emit(str(current.data(256)))

    def _filter_items(self, query: str) -> None:
        query = query.strip().casefold()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())
