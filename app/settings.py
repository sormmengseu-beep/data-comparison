from __future__ import annotations

from pathlib import Path


APP_NAME = "Data Comparison Video Maker"
PROJECT_EXTENSION = ".dcvproject"
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
DEFAULT_FPS = 60
DEFAULT_DURATION = 60.0
DEFAULT_ITEM_DURATION = 3.0
MIN_PREVIEW_COLUMNS_1080P = 3
MAX_PREVIEW_COLUMNS_1080P = 5
MIN_CLIP_DURATION = 0.1

ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECTS_DIR = ROOT_DIR / "projects"
ASSETS_DIR = ROOT_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
TEMPLATES_DIR = ASSETS_DIR / "templates"

SUPPORTED_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"
SUPPORTED_AUDIO_FILTER = "Audio (*.mp3 *.wav *.aac *.m4a *.flac *.ogg)"
SUPPORTED_TEXT_FILTER = "Data files (*.csv *.tsv *.txt *.json);;All files (*.*)"


def ensure_app_directories() -> None:
    for path in (PROJECTS_DIR, ASSETS_DIR, ICONS_DIR, TEMPLATES_DIR):
        path.mkdir(parents=True, exist_ok=True)


COMMON_STYLE = """
* {
    font-family: "Segoe UI";
    font-size: 12px;
}
QMainWindow, QDialog {
    color: @text;
}
QMenuBar {
    background: @chrome;
    color: @textMuted;
    padding: 3px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: @accent;
    color: white;
}
QMenu {
    background: @panel;
    color: @text;
    border: 1px solid @border;
}
QWidget {
    color: @text;
}
QFrame#Panel, QWidget#Panel {
    background: @panel;
    border: 1px solid @border;
}
QWidget#EditorToolbar {
    background: @chrome;
    border-bottom: 1px solid @border;
}
QLabel#AppTitle {
    color: @text;
    font-size: 15px;
    font-weight: 700;
}
QLabel#ProjectTitle {
    color: @textMuted;
}
QLabel#PanelTitle {
    color: @text;
    font-weight: 700;
    letter-spacing: 0px;
}
QPushButton, QToolButton {
    background: @control;
    border: 1px solid @borderStrong;
    border-radius: 6px;
    color: @text;
    padding: 7px 10px;
}
QPushButton:hover, QToolButton:hover {
    background: @controlHover;
}
QPushButton:pressed, QToolButton:pressed {
    background: @accentPressed;
}
QPushButton:checked, QToolButton:checked {
    background: @accent;
    border-color: @accentBorder;
    color: white;
    font-weight: 700;
}
QPushButton#PrimaryButton {
    background: @accent;
    border-color: @accentBorder;
    color: white;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover {
    background: @accentHover;
}
QToolButton#AddIconButton {
    background: @accent;
    border-color: @accentBorder;
    padding: 8px;
}
QToolButton#AddIconButton:hover {
    background: @accentHover;
}
QToolButton#AddIconButton:pressed {
    background: @accentPressed;
}
QToolButton#DangerIconButton {
    background: @dangerBackground;
    border-color: @dangerBorder;
    padding: 6px;
}
QToolButton#DangerIconButton:hover {
    background: @dangerHover;
    border-color: #dc2626;
}
QLineEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: @input;
    border: 1px solid @borderStrong;
    border-radius: 5px;
    color: @text;
    padding: 6px;
    min-height: 22px;
    selection-background-color: @accent;
}
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border-color: @accentBorder;
}
QListWidget {
    background: @input;
    border: 1px solid @border;
    border-radius: 6px;
    outline: 0;
}
QListWidget::item {
    border-radius: 5px;
    padding: 8px;
    margin: 2px;
}
QListWidget::item:selected {
    background: @selection;
    color: white;
}
QScrollArea {
    background: @input;
    border: none;
}
QScrollBar:vertical {
    background: @input;
    width: 10px;
    margin: 0;
}
QScrollBar:horizontal {
    background: @input;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: @borderStrong;
    border-radius: 4px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: @textMuted;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QSlider::groove:horizontal {
    height: 5px;
    background: @borderStrong;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
    background: @accentBorder;
}
QStatusBar {
    background: @chrome;
    color: @textMuted;
}
QSplitter::handle {
    background: @chrome;
}
QSplitter::handle:hover {
    background: @accent;
}
QProgressBar {
    border: 1px solid @border;
    border-radius: 5px;
    background: @input;
    text-align: center;
}
QProgressBar::chunk {
    background: @accent;
    border-radius: 4px;
}
QTabWidget::pane {
    border: 1px solid @border;
    background: @panel;
}
QTabBar::tab {
    background: @control;
    border: 1px solid @border;
    padding: 8px 14px;
}
QTabBar::tab:selected {
    background: @accent;
    color: white;
}
QToolTip {
    background: @panel;
    color: @text;
    border: 1px solid @borderStrong;
}
QLabel#Thumbnail {
    background: @input;
    border: 1px solid @border;
    border-radius: 4px;
}
QWidget#PropertiesContent {
    background: @panel;
}
"""


DARK_COLORS = {
    "@window": "#171a1f",
    "@chrome": "#111418",
    "@panel": "#20242b",
    "@input": "#13171c",
    "@control": "#2a3039",
    "@controlHover": "#343c47",
    "@border": "#303640",
    "@borderStrong": "#3a424e",
    "@text": "#f1f3f5",
    "@textMuted": "#aeb6c2",
    "@selection": "#275da8",
    "@accent": "#2563eb",
    "@accentHover": "#2f6ff4",
    "@accentPressed": "#1f66d1",
    "@accentBorder": "#60a5fa",
    "@dangerBackground": "#3b1d24",
    "@dangerBorder": "#7f1d1d",
    "@dangerHover": "#4c1d24",
}

LIGHT_COLORS = {
    "@window": "#f3f5f8",
    "@chrome": "#ffffff",
    "@panel": "#ffffff",
    "@input": "#f8fafc",
    "@control": "#f1f5f9",
    "@controlHover": "#e2e8f0",
    "@border": "#d9e0e8",
    "@borderStrong": "#b8c3d1",
    "@text": "#172033",
    "@textMuted": "#667085",
    "@selection": "#2563eb",
    "@accent": "#2563eb",
    "@accentHover": "#1d4ed8",
    "@accentPressed": "#1e40af",
    "@accentBorder": "#3b82f6",
    "@dangerBackground": "#fff1f2",
    "@dangerBorder": "#fca5a5",
    "@dangerHover": "#ffe4e6",
}


def app_style(theme: str = "dark") -> str:
    colors = LIGHT_COLORS if theme.lower() == "light" else DARK_COLORS
    style = COMMON_STYLE
    for token in sorted(colors, key=len, reverse=True):
        value = colors[token]
        style = style.replace(token, value)
    return f"QMainWindow, QDialog {{ background: {colors['@window']}; }}\n{style}"


APP_STYLE = app_style("dark")
