from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QButtonGroup, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.settings import MAX_PREVIEW_COLUMNS_1080P, MIN_PREVIEW_COLUMNS_1080P, OPENING_ANIMATION_OPTIONS
from app.utils.icons import IconButton


class TransportControls(QWidget):
    jump_start_requested = Signal()
    step_back_requested = Signal()
    play_pause_requested = Signal()
    stop_requested = Signal()
    step_forward_requested = Signal()
    jump_end_requested = Signal()
    columns_changed = Signal(int)
    opening_animation_changed = Signal(str)
    customize_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("TransportBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(14, 8, 14, 8)
        outer_layout.setSpacing(6)
        layout = QHBoxLayout()
        outer_layout.addLayout(layout)
        layout.setSpacing(12)

        self.jump_start_button = IconButton("first", "Go to start")
        self.step_back_button = IconButton("back", "Back 1 second")
        self.play_button = IconButton("play", "Play (Space)")
        self.stop_button = IconButton("stop", "Stop")
        self.step_forward_button = IconButton("forward", "Forward 1 second")
        self.jump_end_button = IconButton("last", "Go to end")
        playback_group = QWidget()
        playback_group.setObjectName("PlaybackGroup")
        playback_layout = QHBoxLayout(playback_group)
        playback_layout.setContentsMargins(4, 4, 4, 4)
        playback_layout.setSpacing(4)
        self.time_label = QLabel("00:00.000 / 01:00.000")
        self.time_label.setMinimumWidth(180)
        self.time_label.setObjectName("TransportTime")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.column_buttons: dict[int, QPushButton] = {}
        self.column_group = QButtonGroup(self)
        self.column_group.setExclusive(True)

        for button in (
            self.jump_start_button,
            self.step_back_button,
            self.play_button,
            self.stop_button,
            self.step_forward_button,
            self.jump_end_button,
        ):
            button.setObjectName("TransportIconButton")
            button.setFixedSize(34, 34)
            playback_layout.addWidget(button)
        self.play_button.setObjectName("PlaybackButton")
        self.play_button.setFixedSize(40, 40)
        layout.addWidget(playback_group)

        columns_group = QWidget()
        columns_group.setObjectName("ColumnsGroup")
        columns_layout = QHBoxLayout(columns_group)
        columns_layout.setContentsMargins(4, 4, 4, 4)
        columns_layout.setSpacing(2)
        columns_label = QLabel("Columns")
        columns_label.setObjectName("TransportCaption")
        layout.addWidget(columns_label)
        for columns in range(MIN_PREVIEW_COLUMNS_1080P, MAX_PREVIEW_COLUMNS_1080P + 1):
            button = QPushButton(str(columns))
            button.setCheckable(True)
            button.setFixedSize(32, 32)
            button.setObjectName("ColumnButton")
            button.setToolTip(f"Show {columns} columns")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.column_buttons[columns] = button
            self.column_group.addButton(button, columns)
            columns_layout.addWidget(button)
        layout.addWidget(columns_group)
        self.customize_button = IconButton("sliders", "Customize all boxes")
        self.customize_button.setObjectName("TransportIconButton")
        self.customize_button.setFixedSize(36, 36)
        layout.addWidget(self.customize_button)
        layout.addStretch(1)
        layout.addWidget(self.time_label)

        opening_row = QHBoxLayout()
        opening_label = QLabel("Opening animation")
        opening_label.setObjectName("TransportCaption")
        opening_row.addWidget(opening_label)
        self.opening_animation_combo = QComboBox()
        for label, value in OPENING_ANIMATION_OPTIONS:
            self.opening_animation_combo.addItem(label, value)
        self.opening_animation_combo.setToolTip(
            "Animate the first 3, 4, or 5 boxes into place during the opening. "
            "The remaining video keeps the current horizontal scroll."
        )
        opening_row.addWidget(self.opening_animation_combo)
        opening_row.addStretch(1)
        outer_layout.addLayout(opening_row)

        self.jump_start_button.clicked.connect(self.jump_start_requested.emit)
        self.step_back_button.clicked.connect(self.step_back_requested.emit)
        self.play_button.clicked.connect(self.play_pause_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.step_forward_button.clicked.connect(self.step_forward_requested.emit)
        self.jump_end_button.clicked.connect(self.jump_end_requested.emit)
        self.column_group.idClicked.connect(self.columns_changed.emit)
        self.customize_button.clicked.connect(self.customize_requested.emit)
        self.opening_animation_combo.currentIndexChanged.connect(
            lambda _: self.opening_animation_changed.emit(
                str(self.opening_animation_combo.currentData())
            )
        )
        self.set_columns(MIN_PREVIEW_COLUMNS_1080P)

    def set_playing(self, playing: bool) -> None:
        self.play_button.set_icon("pause" if playing else "play", "Pause (Space)" if playing else "Play (Space)")

    def set_time_text(self, text: str) -> None:
        self.time_label.setText(text)

    def set_opening_animation(self, animation: str) -> None:
        self.opening_animation_combo.blockSignals(True)
        self.opening_animation_combo.setCurrentIndex(
            max(0, self.opening_animation_combo.findData(animation))
        )
        self.opening_animation_combo.blockSignals(False)

    def set_columns(self, columns: int) -> None:
        columns = max(MIN_PREVIEW_COLUMNS_1080P, min(MAX_PREVIEW_COLUMNS_1080P, int(columns)))
        button = self.column_buttons.get(columns)
        if button is None:
            return
        self.column_group.blockSignals(True)
        button.setChecked(True)
        self.column_group.blockSignals(False)
