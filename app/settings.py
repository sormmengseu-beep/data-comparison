from __future__ import annotations

import sys
from pathlib import Path


APP_NAME = "Data Comparison Video Maker"
PROJECT_EXTENSION = ".dcvproject"
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080
PROJECT_RESOLUTION_PRESETS = (
    ("HD", 1280, 720),
    ("Full HD", 1920, 1080),
    ("2K / QHD", 2560, 1440),
    ("4K UHD", 3840, 2160),
)
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

def _resource_root() -> Path:
    """Return the read-only root for bundled resources such as icons."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[1]


def _runtime_root() -> Path:
    """Return the writable root used for user projects and exports."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _resource_root()


RESOURCE_ROOT = _resource_root()
ROOT_DIR = _runtime_root()
PROJECTS_DIR = ROOT_DIR / "projects"
ASSETS_DIR = RESOURCE_ROOT / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
TEMPLATES_DIR = ASSETS_DIR / "templates"

SUPPORTED_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.webp)"
SUPPORTED_AUDIO_FILTER = "Audio (*.mp3 *.wav *.aac *.m4a *.flac *.ogg)"
SUPPORTED_TEXT_FILTER = "Data files (*.csv *.tsv *.txt *.json);;All files (*.*)"


def ensure_app_directories() -> None:
    writable_paths = [PROJECTS_DIR, ROOT_DIR / "exports"]
    if not getattr(sys, "frozen", False):
        writable_paths.extend([ASSETS_DIR, ICONS_DIR, TEMPLATES_DIR])
    for path in writable_paths:
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
    border-radius: 8px;
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
    border-radius: 8px;
    border-top-color: @glassEdge;
    font-weight: 700;
    margin-top: 0;
    padding: 12px 14px;
}
QGroupBox#DesignerSection[accentSection="true"] {
    border: 1px solid @accentBorder;
}
QLabel#DesignerPaletteLabel {
    color: @textMuted;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0px;
    padding: 2px 3px 0 3px;
}
QScrollArea#DesignerShapeScroll {
    background: @input;
    border: 1px solid @border;
    border-radius: 8px;
}
QWidget#DesignerShapeGrid {
    background: @input;
}
QScrollArea#DesignerShapeScroll QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 4px;
}
QScrollArea#DesignerShapeScroll QToolButton:hover {
    background: @selectedSurface;
    border: 1px solid @accentBorder;
}
QScrollArea#DesignerShapeScroll QScrollBar:vertical {
    background: @input;
    width: 10px;
    margin: 3px;
}
QScrollArea#DesignerShapeScroll QScrollBar::handle:vertical {
    background: @borderStrong;
    border-radius: 4px;
    min-height: 28px;
}
QScrollArea#DesignerShapeScroll QScrollBar::add-line:vertical,
QScrollArea#DesignerShapeScroll QScrollBar::sub-line:vertical {
    height: 0;
}
QWidget#DesignerPreviewPanel {
    background: @panel;
    border: 1px solid @border;
    border-radius: 8px;
    border-top-color: @glassEdge;
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
    border: 1px solid @border;
    border-radius: 8px;
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
QDialog#BoxCustomizationDialog QWidget#DesignerCompactOption {
    background: @input;
    border: 1px solid @borderStrong;
    border-radius: 8px;
    min-height: 30px;
}
QDialog#BoxCustomizationDialog QWidget#DesignerCompactOption QCheckBox {
    background: transparent;
    border: none;
    padding: 0;
}
QDialog#BoxCustomizationDialog QToolButton#PresetAction {
    border-radius: 8px;
    padding: 0;
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
    background: @selectedSurface;
    color: @selectedText;
}
QMenu {
    background: @popup;
    color: @text;
    border: 1px solid @border;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 4px;
}
QMenu::separator {
    height: 1px;
    background: @border;
    margin: 4px 8px;
}
QWidget {
    color: @text;
}
QFrame#Panel, QWidget#Panel {
    background: @panel;
    border: 1px solid @border;
    border-top-color: @glassEdge;
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
    border-top-color: @glassEdge;
}
QPushButton:hover, QToolButton:hover {
    background: @controlHover;
    border-color: @accentBorder;
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
QPushButton#PrimaryButton, QToolButton#PrimaryButton {
    background: @accent;
    border-color: @accentBorder;
    color: white;
    font-weight: 700;
}
QPushButton#PrimaryButton:hover, QToolButton#PrimaryButton:hover {
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
QPushButton:disabled, QToolButton:disabled,
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {
    color: @textDisabled;
    background: @input;
    border-color: @border;
}
QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border-color: @accentBorder;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
}
QComboBox::down-arrow {
    image: url("@chevron");
    width: 14px;
    height: 14px;
}
QComboBox QAbstractItemView {
    background: @popup;
    color: @text;
    border: 1px solid @borderStrong;
    selection-background-color: @selectedSurface;
    selection-color: @selectedText;
    padding: 4px;
    outline: none;
}
QCheckBox, QRadioButton {
    spacing: 7px;
    color: @text;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid @borderStrong;
    background: @input;
}
QCheckBox::indicator {
    border-radius: 4px;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: @accent;
    border-color: @accentBorder;
}
QCheckBox::indicator:checked {
    image: url("@check");
}
QRadioButton::indicator:checked {
    border: 4px solid @accentBorder;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: @accentBorder;
}
QGroupBox {
    border: 1px solid @border;
    border-top-color: @glassEdge;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 5px;
    left: 8px;
    color: @textMuted;
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
    background: @selectedSurface;
    color: @selectedText;
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
QSlider::sub-page:horizontal {
    background: @accent;
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
    background: @popup;
    color: @text;
    border: 1px solid @borderStrong;
    padding: 6px;
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
    border-radius: 8px;
    border-top-color: @glassEdge;
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
QToolButton#CustomizeButton, QToolButton#ScreenshotButton, QToolButton#BackgroundButton {
    background: @control;
    border: 1px solid @borderStrong;
    border-top-color: @glassEdge;
    border-radius: 8px;
    color: @text;
    padding: 0;
}
QToolButton#CustomizeButton:hover, QToolButton#ScreenshotButton:hover,
QToolButton#BackgroundButton:hover {
    background: @controlHover;
    border-color: @accentBorder;
}
QToolButton#CustomizeButton:pressed, QToolButton#ScreenshotButton:pressed,
QToolButton#BackgroundButton:pressed {
    background: @accentPressed;
    color: white;
}
QToolButton#PlaybackButton {
    background: @accent;
    border: 1px solid @accent;
    border-radius: 8px;
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
QToolButton#CustomizeButton:focus, QToolButton#ScreenshotButton:focus,
QToolButton#BackgroundButton:focus,
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
    border-radius: 8px;
    padding: 3px 8px;
    font-size: 11px;
}
QListWidget#ComparisonItemList {
    background: transparent;
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
    background: @control;
    border: 1px solid @border;
    border-top-color: @glassEdge;
    border-radius: 8px;
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
    "@window": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #394945, stop:0.45 #24292c, stop:1 #292631)",
    "@chrome": "rgba(19, 24, 25, 165)",
    "@panel": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(244, 255, 252, 22), stop:1 rgba(244, 255, 252, 8))",
    "@input": "rgba(10, 17, 18, 100)",
    "@control": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 28), stop:1 rgba(255, 255, 255, 12))",
    "@controlHover": "rgba(228, 255, 246, 38)",
    "@border": "rgba(232, 255, 247, 28)",
    "@borderStrong": "rgba(232, 255, 247, 52)",
    "@glassEdge": "rgba(255, 255, 255, 65)",
    "@popup": "#293331",
    "@base": "#252d2b",
    "@text": "#f2f7f5",
    "@textMuted": "#b2c2bc",
    "@textDisabled": "#768780",
    "@selection": "#2563eb",
    "@selectedSurface": "rgba(59, 130, 246, 35)",
    "@selectedBorder": "#60a5fa",
    "@selectedText": "#dbeafe",
    "@selectedMuted": "#93b5df",
    "@accent": "#2563eb",
    "@accentHover": "#3b75f4",
    "@accentPressed": "#1d4ed8",
    "@accentBorder": "#60a5fa",
    "@dangerBackground": "rgba(244, 99, 126, 24)",
    "@dangerBorder": "#aa6373",
    "@dangerHover": "rgba(244, 99, 126, 50)",
}

LIGHT_COLORS = {
    "@window": "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #d3e8df, stop:0.5 #edf1f0, stop:1 #e7e1ed)",
    "@chrome": "rgba(255, 255, 255, 140)",
    "@panel": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 175), stop:1 rgba(255, 255, 255, 85))",
    "@input": "rgba(255, 255, 255, 115)",
    "@control": "qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 210), stop:1 rgba(255, 255, 255, 95))",
    "@controlHover": "rgba(255, 255, 255, 235)",
    "@border": "rgba(62, 95, 81, 40)",
    "@borderStrong": "rgba(62, 95, 81, 78)",
    "@glassEdge": "rgba(255, 255, 255, 245)",
    "@popup": "#f1f7f4",
    "@base": "#f0f5f2",
    "@text": "#233830",
    "@textMuted": "#526c61",
    "@textDisabled": "#83968c",
    "@selection": "#2563eb",
    "@selectedSurface": "rgba(37, 99, 235, 24)",
    "@selectedBorder": "#3b82f6",
    "@selectedText": "#1d4ed8",
    "@selectedMuted": "#52739b",
    "@accent": "#2563eb",
    "@accentHover": "#1d4ed8",
    "@accentPressed": "#1e40af",
    "@accentBorder": "#3b82f6",
    "@dangerBackground": "rgba(242, 88, 112, 20)",
    "@dangerBorder": "#d88b99",
    "@dangerHover": "rgba(242, 88, 112, 40)",
}


def app_style(theme: str = "dark") -> str:
    normalized = "light" if theme.lower() == "light" else "dark"
    colors = LIGHT_COLORS if normalized == "light" else DARK_COLORS
    style = COMMON_STYLE
    style = style.replace("@chevron", (ICONS_DIR / f"chevron-{normalized}.svg").as_posix())
    style = style.replace("@check", (ICONS_DIR / "check.svg").as_posix())
    for token in sorted(colors, key=len, reverse=True):
        value = colors[token]
        style = style.replace(token, value)
    return f"QMainWindow, QDialog {{ background: {colors['@window']}; }}\n{style}"


APP_STYLE = app_style("dark")
