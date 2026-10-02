from __future__ import annotations

from math import cos, pi, sin

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QBrush, QLinearGradient, QPainterPath


SHAPE_OPTIONS = {
    "rectangle",
    "rounded",
    "pill",
    "circle",
    "ellipse",
    "triangle",
    "diamond",
    "hexagon",
    "star",
}
FILL_OPTIONS = {
    "solid",
    "vertical",
    "vertical_reverse",
    "horizontal",
    "horizontal_reverse",
    "diagonal",
    "diagonal_reverse",
    "diagonal_up",
    "diagonal_up_reverse",
}


def normalized_shape(value: object) -> str:
    shape = str(value or "rectangle")
    return shape if shape in SHAPE_OPTIONS else "rectangle"


def shape_path(rect: QRectF, shape: object, corner_radius: float = 0.0) -> QPainterPath:
    """Return the clipping/fill path used by both the designer and final render."""
    path = QPainterPath()
    kind = normalized_shape(shape)
    if kind == "circle":
        diameter = min(rect.width(), rect.height())
        circle = QRectF(0, 0, diameter, diameter)
        circle.moveCenter(rect.center())
        path.addEllipse(circle)
    elif kind == "ellipse":
        path.addEllipse(rect)
    elif kind == "triangle":
        path.moveTo(rect.center().x(), rect.top())
        path.lineTo(rect.right(), rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()
    elif kind == "diamond":
        path.moveTo(rect.center().x(), rect.top())
        path.lineTo(rect.right(), rect.center().y())
        path.lineTo(rect.center().x(), rect.bottom())
        path.lineTo(rect.left(), rect.center().y())
        path.closeSubpath()
    elif kind == "hexagon":
        quarter = rect.width() / 4.0
        path.moveTo(rect.left() + quarter, rect.top())
        path.lineTo(rect.right() - quarter, rect.top())
        path.lineTo(rect.right(), rect.center().y())
        path.lineTo(rect.right() - quarter, rect.bottom())
        path.lineTo(rect.left() + quarter, rect.bottom())
        path.lineTo(rect.left(), rect.center().y())
        path.closeSubpath()
    elif kind == "star":
        center = rect.center()
        outer = min(rect.width(), rect.height()) / 2.0
        inner = outer * 0.45
        for index in range(10):
            radius = outer if index % 2 == 0 else inner
            angle = -pi / 2.0 + index * pi / 5.0
            point = QPointF(
                center.x() + cos(angle) * radius,
                center.y() + sin(angle) * radius,
            )
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        path.closeSubpath()
    elif kind == "pill":
        radius = min(rect.width(), rect.height()) / 2.0
        path.addRoundedRect(rect, radius, radius)
    elif kind == "rounded":
        radius = corner_radius or min(18.0, rect.width() / 8.0, rect.height() / 8.0)
        path.addRoundedRect(rect, radius, radius)
    else:
        path.addRect(rect)
    return path


def fill_brush(
    rect: QRectF,
    first_color: object,
    second_color: object,
    mode: object,
) -> QBrush:
    first = QColor(str(first_color or "#111827"))
    second = QColor(str(second_color or first.name()))
    fill_mode = str(mode or "solid")
    if fill_mode not in FILL_OPTIONS or fill_mode == "solid":
        return QBrush(first)
    if fill_mode == "horizontal":
        gradient = QLinearGradient(rect.topLeft(), rect.topRight())
    elif fill_mode == "horizontal_reverse":
        gradient = QLinearGradient(rect.topRight(), rect.topLeft())
    elif fill_mode == "diagonal":
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    elif fill_mode == "diagonal_reverse":
        gradient = QLinearGradient(rect.bottomRight(), rect.topLeft())
    elif fill_mode == "diagonal_up":
        gradient = QLinearGradient(rect.bottomLeft(), rect.topRight())
    elif fill_mode == "diagonal_up_reverse":
        gradient = QLinearGradient(rect.topRight(), rect.bottomLeft())
    elif fill_mode == "vertical_reverse":
        gradient = QLinearGradient(rect.bottomLeft(), rect.topLeft())
    else:
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    gradient.setColorAt(0.0, first)
    gradient.setColorAt(1.0, second)
    return QBrush(gradient)
