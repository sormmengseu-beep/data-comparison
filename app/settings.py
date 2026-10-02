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
OPENING_ANIMATION_OPTIONS = (
    ("Left to right (default)", "slide_left"),
    ("Bottom to fit", "from_bottom"),
    ("Top to fit", "from_top"),
    ("Staggered bottom to fit", "stagger_bottom"),
    ("Staggered top to fit", "stagger_top"),
    ("Alternating top and bottom", "alternating"),
    ("Fade in", "fade_in"),
    ("Zoom in", "zoom_in"),
    ("Pop in", "pop_in"),
    ("Bounce from bottom", "bounce_bottom"),
    ("Reveal left to right", "reveal_left"),
)

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
QDialog#BoxCustomizationDialog {
    background: @window;
}
QWidget#DesignerHeader {
    background: transparent;
    border-bottom: 1px solid @border;
    padding-bottom: 10px;
}
QLabel#DesignerTitle {
    color: @text;
    font-size: 20px;
    font-weight: 700;
}
QLabel#DesignerSubtitle, QLabel#DesignerHint {
    color: @textMuted;
}
QLabel#DesignerBadge {
    background: @selectedSurface;
    border: 1px solid @accentBorder;
    border-radius: 10px;
    color: @accentBorder;
    font-size: 10px;
    font-weight: 700;
    padding: 5px 10px;
}
QScrollArea#DesignerInspectorScroll {
    background: transparent;
    border: none;
}
QWidget#DesignerInspector {
    background: transparent;
}
QGroupBox#DesignerSection {
    background: @panel;
    border: 1px solid @border;
    border-radius: 12px;
    font-weight: 700;
    margin-top: 18px;
    padding: 18px 14px 14px 14px;
}
QGroupBox#DesignerSection::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 7px;
    color: @text;
    background: @panel;
}
QGroupBox#DesignerSection[accentSection="true"] {
    border: 1px solid @accentBorder;
}
QWidget#DesignerPreviewPanel {
    background: @panel;
    border: 1px solid @border;
    border-radius: 14px;
}
QLabel#DesignerPreviewTitle {
    color: @text;
    font-size: 15px;
    font-weight: 700;
}
QWidget#DesignerFooter {
    background: transparent;
    border-top: 1px solid @border;
}
QListWidget#DesignerOrderList {
    background: @input;
    border: 1px solid @accentBorder;
    border-radius: 10px;
    padding: 4px;
    outline: none;
}
QListWidget#DesignerOrderList::item {
    background: transparent;
    border: none;
    padding: 0;
}
QDialog#BoxCustomizationDialog QLineEdit,
QDialog#BoxCustomizationDialog QDoubleSpinBox,
QDialog#BoxCustomizationDialog QSpinBox,
QDialog#BoxCustomizationDialog QComboBox {
    border-radius: 8px;
    min-height: 28px;
}
QDialog#BoxCustomizationDialog QPushButton {
    border-radius: 8px;
    min-height: 26px;
}
QDialog#BoxCustomizationDialog QPushButton#PresetAction {
    min-width: 58px;
    padding-left: 9px;
    padding-right: 9px;
}
QDialog#BoxCustomizationDialog QDialogButtonBox QPushButton {
    min-width: 82px;
    padding: 8px 16px;
}
QSplitter#DesignerSplitter::handle {
    background: transparent;
    margin: 8px 2px;
}
QSplitter#DesignerSplitter::handle:hover {
    background: @selectedSurface;
    border-radius: 3px;
}
QScrollArea#DesignerInspectorScroll QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollArea#DesignerInspectorScroll QScrollBar::handle:vertical {
    background: @borderStrong;
    border-radius: 4px;
    min-height: 32px;
}
QScrollArea#DesignerInspectorScroll QScrollBar::handle:vertical:hover {
    background: @textMuted;
}
QScrollArea#DesignerInspectorScroll QScrollBar::add-line:vertical,
QScrollArea#DesignerInspectorScroll QScrollBar::sub-line:vertical {
    height: 0;
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
QWidget#TransportBar {
    background: @chrome;
    border-top: 1px solid @border;
}
QWidget#PlaybackGroup, QWidget#ColumnsGroup {
    background: @input;
    border: 1px solid @border;
    border-radius: 12px;
}
QToolButton#TransportIconButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0;
    color: @textMuted;
}
QToolButton#TransportIconButton:hover {
    background: @controlHover;
    color: @text;
}
QToolButton#TransportIconButton:pressed {
    background: @border;
}
QToolButton#PlaybackButton {
    background: @accent;
    border: 1px solid @accent;
    border-radius: 10px;
    padding: 0;
    color: white;
}
QToolButton#PlaybackButton:hover {
    background: @accentHover;
}
QToolButton#PlaybackButton:pressed {
    background: @accentPressed;
}
QToolButton#TransportIconButton:focus, QToolButton#PlaybackButton:focus,
QToolButton#ItemEditButton:focus {
    border: 1px solid @accentBorder;
}
QPushButton#ColumnButton {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
    color: @textMuted;
}
QPushButton#ColumnButton:hover {
    background: @controlHover;
}
QPushButton#ColumnButton:checked {
    background: @accent;
    color: white;
}
QLabel#TransportCaption, QLabel#TransportTime {
    color: @textMuted;
}
QLabel#TransportTime {
    font-family: "Consolas";
    font-size: 11px;
}
QLabel#ItemCount {
    background: @input;
    color: @textMuted;
    border: 1px solid @border;
    border-radius: 10px;
    padding: 3px 8px;
    font-size: 11px;
}
QListWidget#ComparisonItemList {
    background: @panel;
    border: none;
}
QListWidget#ComparisonItemList::item {
    padding: 0;
    margin: 3px 0;
    color: transparent;
    background: transparent;
    border: none;
}
QListWidget#ComparisonItemList::item:selected {
    color: transparent;
    background: transparent;
}
QWidget#ComparisonItemRow {
    background: @input;
    border: 1px solid @border;
    border-radius: 10px;
}
QWidget#ComparisonItemRow:hover {
    border-color: @borderStrong;
}
QWidget#ComparisonItemRow[selected="true"] {
    background: @selectedSurface;
    border-color: @selectedBorder;
}
QLabel#ItemThumbnail {
    background: @control;
    color: @textMuted;
    border: none;
    border-radius: 7px;
}
QLabel#ComparisonItemName {
    color: @text;
    font-size: 13px;
    font-weight: 600;
    border: none;
    background: transparent;
}
QLabel#ComparisonItemDetails {
    color: @textMuted;
    font-size: 11px;
    border: none;
    background: transparent;
}
QWidget#ComparisonItemRow[selected="true"] QLabel#ComparisonItemName {
    color: @selectedText;
}
QWidget#ComparisonItemRow[selected="true"] QLabel#ComparisonItemDetails {
    color: @selectedMuted;
}
QToolButton#ItemEditButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0;
    color: @textMuted;
}
QToolButton#ItemEditButton:hover {
    background: @controlHover;
    color: @text;
}
QToolButton#ItemEditButton:pressed {
    background: @border;
}
QWidget#ComparisonItemRow[selected="true"] QToolButton#ItemEditButton {
    color: @selectedText;
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
    "@selectedSurface": "#182d4b",
    "@selectedBorder": "#3b82f6",
    "@selectedText": "#dbeafe",
    "@selectedMuted": "#93b5df",
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
    "@selectedSurface": "#eff6ff",
    "@selectedBorder": "#93c5fd",
    "@selectedText": "#1d4ed8",
    "@selectedMuted": "#52739b",
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
