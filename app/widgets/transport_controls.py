from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget

from app.settings import MAX_PREVIEW_COLUMNS_1080P, MIN_PREVIEW_COLUMNS_1080P


class TransportControls(QWidget):
    jump_start_requested = Signal()
    step_back_requested = Signal()
    play_pause_requested = Signal()
    stop_requested = Signal()
    step_forward_requested = Signal()
    jump_end_requested = Signal()
    columns_changed = Signal(int)
    customize_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        self.jump_start_button = QPushButton("|<<")
        self.step_back_button = QPushButton("<<")
        self.play_button = QPushButton("Play")
        self.stop_button = QPushButton("Stop")
        self.step_forward_button = QPushButton(">>")
        self.jump_end_button = QPushButton(">>|")
        self.time_label = QLabel("00:00.000 / 01:00.000")
        self.time_label.setMinimumWidth(180)
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
            button.setFixedHeight(34)
            layout.addWidget(button)
        layout.addSpacing(10)
        layout.addWidget(QLabel("Columns"))
        for columns in range(MIN_PREVIEW_COLUMNS_1080P, MAX_PREVIEW_COLUMNS_1080P + 1):
            button = QPushButton(str(columns))
            button.setCheckable(True)
            button.setFixedSize(34, 34)
            self.column_buttons[columns] = button
            self.column_group.addButton(button, columns)
            layout.addWidget(button)
        self.customize_button = QPushButton("Customize")
        self.customize_button.setFixedHeight(34)
        layout.addWidget(self.customize_button)
        layout.addStretch(1)
        layout.addWidget(self.time_label)

        self.jump_start_button.clicked.connect(self.jump_start_requested.emit)
        self.step_back_button.clicked.connect(self.step_back_requested.emit)
        self.play_button.clicked.connect(self.play_pause_requested.emit)
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.step_forward_button.clicked.connect(self.step_forward_requested.emit)
        self.jump_end_button.clicked.connect(self.jump_end_requested.emit)
        self.column_group.idClicked.connect(self.columns_changed.emit)
        self.customize_button.clicked.connect(self.customize_requested.emit)
        self.set_columns(MIN_PREVIEW_COLUMNS_1080P)

    def set_playing(self, playing: bool) -> None:
        self.play_button.setText("Pause" if playing else "Play")

    def set_time_text(self, text: str) -> None:
        self.time_label.setText(text)

    def set_columns(self, columns: int) -> None:
        columns = max(MIN_PREVIEW_COLUMNS_1080P, min(MAX_PREVIEW_COLUMNS_1080P, int(columns)))
        button = self.column_buttons.get(columns)
        if button is None:
            return
        self.column_group.blockSignals(True)
        button.setChecked(True)
        self.column_group.blockSignals(False)
