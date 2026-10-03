from __future__ import annotations

from PySide6.QtCore import QByteArray, QEvent, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QToolButton


ICON_PATHS = {
    "first": '<path d="M5 5v14M19 6l-8 6 8 6z"/>',
    "back": '<path d="m14 6-6 6 6 6"/>',
    "play": '<path d="m8 5 11 7-11 7z" fill="currentColor" stroke="none"/>',
    "pause": '<path d="M8 5v14M16 5v14" stroke-width="3"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
    "forward": '<path d="m10 6 6 6-6 6"/>',
    "last": '<path d="M19 5v14M5 6l8 6-8 6z"/>',
    "edit": '<path d="m15 5 4 4M4 20l4-1 12-12a2.8 2.8 0 0 0-4-4L4 15z"/>',
    "sliders": '<path d="M4 7h5m5 0h6M4 17h10m5 0h1"/><circle cx="11.5" cy="7" r="2.5"/><circle cx="16.5" cy="17" r="2.5"/>',
    "settings": '<path d="M9.5 2h5l.5 3 2 1.2 2.8-1.1 2.5 4.3-2.3 2v1.2l2.3 2-2.5 4.3-2.8-1.1-2 1.2-.5 3h-5l-.5-3-2-1.2-2.8 1.1-2.5-4.3 2.3-2v-1.2l-2.3-2 2.5-4.3 2.8 1.1L9 5z"/><circle cx="12" cy="12" r="3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2zM7 3v6h10M7 21v-8h10v8"/>',
    "trash": '<path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 5-5 4 4 4-6 5 7"/>',
    "camera": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z"/><circle cx="12" cy="13" r="4"/>',
    "file": '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5"/>',
    "music": '<path d="M9 18V5l11-2v13M9 8l11-2"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="17" cy="16" rx="3" ry="3"/>',
}


def make_icon(name: str, color: QColor | str) -> QIcon:
    color = QColor(color).name()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" color="{color}" stroke="{color}" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        f'{ICON_PATHS[name]}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    for size in (18, 20, 24, 36, 40, 48):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class IconButton(QToolButton):
    """An accessible icon button that follows the widget's theme colors."""

    def __init__(self, icon_name: str, label: str, parent=None) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setIconSize(QSize(20, 20))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_icon(icon_name, label)

    def set_icon(self, icon_name: str, label: str) -> None:
        self._icon_name = icon_name
        self.setToolTip(label)
        self.setAccessibleName(label)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        self.setIcon(make_icon(self._icon_name, self.palette().color(QPalette.ColorRole.ButtonText)))

    def event(self, event) -> bool:
        result = super().event(event)
        if hasattr(self, "_icon_name") and event.type() in (
            QEvent.Type.PaletteChange, QEvent.Type.StyleChange, QEvent.Type.Polish,
        ):
            self._refresh_icon()
        return result
