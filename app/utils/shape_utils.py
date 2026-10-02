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
    "triangle_down",
    "diamond",
    "pentagon",
    "hexagon",
    "octagon",
    "star",
    "burst",
    "chevron",
    "arrow_left",
    "arrow_right",
    "parallelogram",
    "trapezoid",
    "cross",
    "heart",
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
    elif kind == "triangle_down":
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.center().x(), rect.bottom())
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
    elif kind in {"pentagon", "octagon", "burst"}:
        points = {"pentagon": 5, "octagon": 8, "burst": 12}[kind]
        center = rect.center()
        outer = min(rect.width(), rect.height()) / 2.0
        point_count = points * 2 if kind == "burst" else points
        for index in range(point_count):
            radius = outer
            if kind == "burst" and index % 2:
                radius *= 0.72
            angle = -pi / 2.0 + index * (2.0 * pi / point_count)
            point = QPointF(
                center.x() + cos(angle) * radius,
                center.y() + sin(angle) * radius,
            )
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
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
    elif kind == "chevron":
        notch = rect.width() * 0.28
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right() - notch, rect.top())
        path.lineTo(rect.right(), rect.center().y())
        path.lineTo(rect.right() - notch, rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.lineTo(rect.left() + notch, rect.center().y())
        path.closeSubpath()
    elif kind in {"arrow_left", "arrow_right"}:
        left, right = rect.left(), rect.right()
        if kind == "arrow_left":
            left, right = right, left
        direction = 1.0 if right > left else -1.0
        neck = left + direction * rect.width() * 0.42
        path.moveTo(right, rect.center().y())
        path.lineTo(neck, rect.top())
        path.lineTo(neck, rect.top() + rect.height() * 0.28)
        path.lineTo(left, rect.top() + rect.height() * 0.28)
        path.lineTo(left, rect.bottom() - rect.height() * 0.28)
        path.lineTo(neck, rect.bottom() - rect.height() * 0.28)
        path.lineTo(neck, rect.bottom())
        path.closeSubpath()
    elif kind == "parallelogram":
        offset = rect.width() * 0.2
        path.moveTo(rect.left() + offset, rect.top())
        path.lineTo(rect.right(), rect.top())
        path.lineTo(rect.right() - offset, rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()
    elif kind == "trapezoid":
        offset = rect.width() * 0.18
        path.moveTo(rect.left() + offset, rect.top())
        path.lineTo(rect.right() - offset, rect.top())
        path.lineTo(rect.right(), rect.bottom())
        path.lineTo(rect.left(), rect.bottom())
        path.closeSubpath()
    elif kind == "cross":
        x1 = rect.left() + rect.width() / 3.0
        x2 = rect.right() - rect.width() / 3.0
        y1 = rect.top() + rect.height() / 3.0
        y2 = rect.bottom() - rect.height() / 3.0
        path.moveTo(x1, rect.top())
        path.lineTo(x2, rect.top())
        path.lineTo(x2, y1)
        path.lineTo(rect.right(), y1)
        path.lineTo(rect.right(), y2)
        path.lineTo(x2, y2)
        path.lineTo(x2, rect.bottom())
        path.lineTo(x1, rect.bottom())
        path.lineTo(x1, y2)
        path.lineTo(rect.left(), y2)
        path.lineTo(rect.left(), y1)
        path.lineTo(x1, y1)
        path.closeSubpath()
    elif kind == "heart":
        path.moveTo(rect.center().x(), rect.bottom())
        path.cubicTo(
            rect.left() - rect.width() * 0.08,
            rect.center().y() + rect.height() * 0.18,
            rect.left(),
            rect.top() + rect.height() * 0.12,
            rect.left() + rect.width() * 0.25,
            rect.top() + rect.height() * 0.12,
        )
        path.cubicTo(
            rect.center().x() - rect.width() * 0.06,
            rect.top() + rect.height() * 0.12,
            rect.center().x() - rect.width() * 0.02,
            rect.top() + rect.height() * 0.28,
            rect.center().x(),
            rect.top() + rect.height() * 0.32,
        )
        path.cubicTo(
            rect.center().x() + rect.width() * 0.02,
            rect.top() + rect.height() * 0.28,
            rect.center().x() + rect.width() * 0.06,
            rect.top() + rect.height() * 0.12,
            rect.right() - rect.width() * 0.25,
            rect.top() + rect.height() * 0.12,
        )
        path.cubicTo(
            rect.right(),
            rect.top() + rect.height() * 0.12,
            rect.right() + rect.width() * 0.08,
            rect.center().y() + rect.height() * 0.18,
            rect.center().x(),
            rect.bottom(),
        )
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
