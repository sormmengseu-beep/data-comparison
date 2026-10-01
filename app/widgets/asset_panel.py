from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.comparison_item import ComparisonItem


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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("ASSETS")
        title.setObjectName("PanelTitle")
        self.count_label = QLabel("0 items")
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
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
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
        for item in items:
            list_item = QListWidgetItem(f"{item.name}\n{item.rank}  {item.value}".strip())
            list_item.setData(256, item.id)
            self.list_widget.addItem(list_item)
            if item.id == selected_id:
                self.list_widget.setCurrentItem(list_item)
        self.list_widget.blockSignals(False)
        self._filter_items(self.search_edit.text())

    def select_item(self, item_id: str) -> None:
        self.list_widget.blockSignals(True)
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            if item.data(256) == item_id:
                self.list_widget.setCurrentItem(item)
                break
        self.list_widget.blockSignals(False)

    def _current_item_changed(self, current: QListWidgetItem | None) -> None:
        if current is not None:
            self.item_selected.emit(str(current.data(256)))

    def _filter_items(self, query: str) -> None:
        query = query.strip().casefold()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            item.setHidden(bool(query) and query not in item.text().casefold())
