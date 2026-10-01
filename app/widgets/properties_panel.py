from __future__ import annotations

from PySide6.QtCore import QSize, Signal, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.models.comparison_item import ComparisonItem
from app.settings import MIN_CLIP_DURATION
from app.utils.image_utils import ImageCache


class PropertiesPanel(QWidget):
    item_changed = Signal(dict)
    browse_image_requested = Signal()
    customize_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self._current_id = ""
        self._image_cache = ImageCache()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("PROPERTIES")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.empty_label = QLabel("Select an item or clip to edit its properties.")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        self.form_widget = QWidget()
        form = QFormLayout(self.form_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(9)

        self.name_edit = QLineEdit()
        self.rank_edit = QLineEdit()
        self.category_edit = QLineEdit()
        self.value_edit = QLineEdit()
        self.image_label = QLineEdit()
        self.image_label.setReadOnly(True)
        self.browse_button = QPushButton("Browse...")
        image_row = QWidget()
        image_layout = QHBoxLayout(image_row)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.addWidget(self.image_label, 1)
        image_layout.addWidget(self.browse_button)

        self.thumbnail = QLabel()
        self.thumbnail.setObjectName("Thumbnail")
        self.thumbnail.setFixedSize(120, 72)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.customize_button = QPushButton("Customize Box")
        self.customize_button.setObjectName("PrimaryButton")

        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(0.0, 24 * 60 * 60)
        self.start_spin.setDecimals(3)
        self.start_spin.setSingleStep(0.1)
        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(MIN_CLIP_DURATION, 24 * 60 * 60)
        self.duration_spin.setDecimals(3)
        self.duration_spin.setSingleStep(0.1)

        self.animation_combo = QComboBox()
        self.animation_combo.addItems(
            ["slide_left", "slide_right", "fade_in", "pop", "rise", "none"]
        )

        form.addRow("Name", self.name_edit)
        form.addRow("Rank", self.rank_edit)
        form.addRow("Category", self.category_edit)
        form.addRow("Value", self.value_edit)
        form.addRow("Image", image_row)
        form.addRow("Thumbnail", self.thumbnail)
        form.addRow("Design", self.customize_button)
        form.addRow("Start Time", self.start_spin)
        form.addRow("Duration", self.duration_spin)
        form.addRow("Animation", self.animation_combo)
        layout.addWidget(self.form_widget)
        layout.addStretch(1)

        self.browse_button.clicked.connect(self.browse_image_requested.emit)
        self.customize_button.clicked.connect(
            lambda: self.customize_requested.emit(self._current_id)
        )
        self.name_edit.textEdited.connect(lambda text: self._emit_change("name", text))
        self.rank_edit.textEdited.connect(lambda text: self._emit_change("rank", text))
        self.category_edit.textEdited.connect(lambda text: self._emit_change("category", text))
        self.value_edit.textEdited.connect(lambda text: self._emit_change("value", text))
        self.start_spin.valueChanged.connect(lambda value: self._emit_change("start_time", value))
        self.duration_spin.valueChanged.connect(lambda value: self._emit_change("duration", value))
        self.animation_combo.currentTextChanged.connect(
            lambda text: self._emit_change("animation", text)
        )
        self.set_item(None)

    def set_item(self, item: ComparisonItem | None) -> None:
        self._current_id = item.id if item else ""
        self.empty_label.setVisible(item is None)
        self.form_widget.setVisible(item is not None)
        controls = [
            self.name_edit,
            self.rank_edit,
            self.category_edit,
            self.value_edit,
            self.image_label,
            self.start_spin,
            self.duration_spin,
            self.animation_combo,
        ]
        for control in controls:
            control.blockSignals(True)
        if item is not None:
            self.name_edit.setText(item.name)
            self.rank_edit.setText(item.rank)
            self.category_edit.setText(item.category)
            self.value_edit.setText(item.value)
            self.image_label.setText(item.image_path)
            self.start_spin.setValue(item.start_time)
            self.duration_spin.setValue(item.duration)
            index = self.animation_combo.findText(item.animation)
            self.animation_combo.setCurrentIndex(max(0, index))
            self._set_thumbnail(item.image_path)
        for control in controls:
            control.blockSignals(False)

    def set_image_path(self, path: str) -> None:
        self.image_label.setText(path)
        self._set_thumbnail(path)
        self._emit_change("image_path", path)

    def _set_thumbnail(self, path: str) -> None:
        pixmap = self._image_cache.pixmap(path, QSize(120, 72))
        canvas = QPixmap(120, 72)
        canvas.fill(Qt.GlobalColor.transparent)
        self.thumbnail.setPixmap(pixmap)

    def _emit_change(self, key: str, value: object) -> None:
        if self._current_id:
            self.item_changed.emit({"id": self._current_id, key: value})
