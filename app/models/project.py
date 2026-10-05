from __future__ import annotations

from dataclasses import dataclass, field

from app.settings import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    DEFAULT_DURATION,
    DEFAULT_FPS,
    DEFAULT_ITEM_DURATION,
    MAX_PREVIEW_COLUMNS_1080P,
    MIN_PREVIEW_COLUMNS_1080P,
    MIN_CLIP_DURATION,
    OPENING_ANIMATION_OPTIONS,
)
from app.models.comparison_item import ComparisonItem
from app.models.timeline_item import TimelineItem


@dataclass
class Project:
    name: str = "Football Comparison"
    width: int = CANVAS_WIDTH
    height: int = CANVAS_HEIGHT
    fps: int = DEFAULT_FPS
    duration: float = DEFAULT_DURATION
    background: str = "Dark"
    preview_max_columns: int = MIN_PREVIEW_COLUMNS_1080P
    item_fixed_duration: float = DEFAULT_ITEM_DURATION
    opening_animation: str = "slide_left"
    canvas_background_color: str = "#05070a"
    canvas_background_image: str = ""
    canvas_background_fit: str = "cover"
    card_border_color: str = "#05070a"
    card_border_width: int = 3
    name_background_color: str = "#f45b69"
    name_text_color: str = "#ffffff"
    category_background_color: str = "#050505"
    category_text_color: str = "#ffffff"
    rank_background_color: str = "#fbb10b"
    rank_text_color: str = "#080808"
    value_background_color: str = "#087be8"
    value_text_color: str = "#ffffff"
    text_font_family: str = "Segoe UI"
    text_font_size: int = 0
    image_fit: str = "cover"
    image_height_percent_3: int = 56
    image_height_percent_4: int = 58
    image_height_percent_5: int = 60
    field_styles: dict[str, dict[str, str]] = field(default_factory=dict)
    comparison_items: list[ComparisonItem] = field(default_factory=list)
    timeline_clips: list[TimelineItem] = field(default_factory=list)
    audio_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.name,
            "resolution": {"width": self.width, "height": self.height},
            "fps": self.fps,
            "duration": self.duration,
            "background": self.background,
            "preview_max_columns": self.preview_max_columns,
            "item_fixed_duration": self.item_fixed_duration,
            "opening_animation": self.opening_animation,
            "style": {
                "canvas_background_color": self.canvas_background_color,
                "canvas_background_image": self.canvas_background_image,
                "canvas_background_fit": self.canvas_background_fit,
                "card_border_color": self.card_border_color,
                "card_border_width": self.card_border_width,
                "name_background_color": self.name_background_color,
                "name_text_color": self.name_text_color,
                "category_background_color": self.category_background_color,
                "category_text_color": self.category_text_color,
                "rank_background_color": self.rank_background_color,
                "rank_text_color": self.rank_text_color,
                "value_background_color": self.value_background_color,
                "value_text_color": self.value_text_color,
                "text_font_family": self.text_font_family,
                "text_font_size": self.text_font_size,
                "image_fit": self.image_fit,
                "image_height_percent_3": self.image_height_percent_3,
                "image_height_percent_4": self.image_height_percent_4,
                "image_height_percent_5": self.image_height_percent_5,
                "field_styles": self.field_styles,
            },
            "comparison_items": [item.to_dict() for item in self.comparison_items],
            "timeline_clips": [clip.to_dict() for clip in self.timeline_clips],
            "audio_paths": list(self.audio_paths),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        resolution = data.get("resolution") or {}
        style = data.get("style") or {}
        opening_animation = str(data.get("opening_animation") or "slide_left")
        if opening_animation not in {value for _, value in OPENING_ANIMATION_OPTIONS}:
            opening_animation = "slide_left"
        project = cls(
            name=str(data.get("project_name") or data.get("name") or "Untitled Project"),
            width=_project_dimension(resolution.get("width"), CANVAS_WIDTH, 320, 7680),
            height=_project_dimension(resolution.get("height"), CANVAS_HEIGHT, 240, 4320),
            fps=int(data.get("fps") or DEFAULT_FPS),
            duration=max(1.0, float(data.get("duration") or DEFAULT_DURATION)),
            background=str(data.get("background") or "Dark"),
            preview_max_columns=int(data.get("preview_max_columns") or MIN_PREVIEW_COLUMNS_1080P),
            opening_animation=opening_animation,
            item_fixed_duration=max(
                MIN_CLIP_DURATION,
                float(data.get("item_fixed_duration") or DEFAULT_ITEM_DURATION),
            ),
            canvas_background_color=str(style.get("canvas_background_color") or "#05070a"),
            canvas_background_image=str(style.get("canvas_background_image") or ""),
            canvas_background_fit=(
                str(style.get("canvas_background_fit"))
                if str(style.get("canvas_background_fit")) in {"cover", "contain", "stretch"}
                else "cover"
            ),
            card_border_color=str(style.get("card_border_color") or "#05070a"),
            card_border_width=_card_border_width(style.get("card_border_width")),
            name_background_color=str(style.get("name_background_color") or "#f45b69"),
            name_text_color=str(style.get("name_text_color") or "#ffffff"),
            category_background_color=str(style.get("category_background_color") or "#050505"),
            category_text_color=str(style.get("category_text_color") or "#ffffff"),
            rank_background_color=str(style.get("rank_background_color") or "#fbb10b"),
            rank_text_color=str(style.get("rank_text_color") or "#080808"),
            value_background_color=str(style.get("value_background_color") or "#087be8"),
            value_text_color=str(style.get("value_text_color") or "#ffffff"),
            text_font_family=str(style.get("text_font_family") or "Segoe UI"),
            text_font_size=_font_size(style.get("text_font_size")),
            image_fit=(
                str(style.get("image_fit") or "cover")
                if str(style.get("image_fit") or "cover") in {"cover", "contain", "stretch"}
                else "cover"
            ),
            image_height_percent_3=_layout_height(style.get("image_height_percent_3"), 56),
            image_height_percent_4=_layout_height(style.get("image_height_percent_4"), 58),
            image_height_percent_5=_layout_height(style.get("image_height_percent_5"), 60),
            field_styles=_field_styles(style.get("field_styles")),
            comparison_items=[
                ComparisonItem.from_dict(item) for item in data.get("comparison_items", [])
            ],
            timeline_clips=[
                TimelineItem.from_dict(clip) for clip in data.get("timeline_clips", [])
            ],
            audio_paths=[str(path) for path in data.get("audio_paths", [])],
        )
        if project.fps not in (30, 60):
            project.fps = DEFAULT_FPS
        project.preview_max_columns = max(
            MIN_PREVIEW_COLUMNS_1080P,
            min(MAX_PREVIEW_COLUMNS_1080P, project.preview_max_columns),
        )
        project.apply_fixed_item_timing()
        return project

    @classmethod
    def sample(cls) -> "Project":
        items = [
            ComparisonItem(
                id="item_juventus",
                name="Juventus",
                rank="11th",
                category="NET WORTH",
                value="$2.05 billion",
                start_time=0.0,
                duration=DEFAULT_ITEM_DURATION,
                animation="slide_left",
            ),
            ComparisonItem(
                id="item_arsenal",
                name="Arsenal",
                rank="10th",
                category="NET WORTH",
                value="$2.6 billion",
                start_time=DEFAULT_ITEM_DURATION,
                duration=DEFAULT_ITEM_DURATION,
                animation="slide_left",
            ),
            ComparisonItem(
                id="item_chelsea",
                name="Chelsea",
                rank="9th",
                category="NET WORTH",
                value="$3.13 billion",
                start_time=DEFAULT_ITEM_DURATION * 2,
                duration=DEFAULT_ITEM_DURATION,
                animation="slide_left",
            ),
        ]
        return cls(comparison_items=items)

    def item_by_id(self, item_id: str) -> ComparisonItem | None:
        for item in self.comparison_items:
            if item.id == item_id:
                return item
        return None

    def total_duration(self) -> float:
        return self.content_duration()

    def content_duration(self) -> float:
        if not self.comparison_items:
            return 0.0
        fixed_duration = max(MIN_CLIP_DURATION, self.item_fixed_duration)
        return len(self.comparison_items) * fixed_duration

    def apply_fixed_item_timing(self) -> None:
        fixed_duration = max(MIN_CLIP_DURATION, self.item_fixed_duration)
        for index, item in enumerate(self.comparison_items):
            item.start_time = index * fixed_duration
            item.duration = fixed_duration
        self.duration = self.content_duration()


def _font_size(value: object) -> int:
    try:
        return max(0, min(120, int(value)))
    except (TypeError, ValueError):
        return 0


def _layout_height(value: object, default: int) -> int:
    try:
        return max(35, min(75, int(value)))
    except (TypeError, ValueError):
        return default


def _project_dimension(
    value: object, default: int, minimum: int, maximum: int
) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _card_border_width(value: object) -> int:
    """Normalize the outer card border while keeping old projects at 3 px."""
    try:
        return max(0, min(40, int(value)))
    except (TypeError, ValueError):
        return 3


def _field_styles(value: object) -> dict[str, dict[str, str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, dict[str, str]] = {}
    for field_id, raw_style in value.items():
        if not isinstance(raw_style, dict):
            continue
        style = {
            "background_color": str(raw_style.get("background_color") or ""),
            "text_color": str(raw_style.get("text_color") or ""),
        }
        for key, default, minimum, maximum in (
            ("outline_width", 0, 0, 8),
            ("border_width", 0, 0, 12),
            ("font_size", 0, 0, 120),
            ("height_weight", 100, 25, 400),
            ("padding", 14, 0, 64),
            ("inset", 0, 0, 96),
            ("corner_radius", 0, 0, 64),
            ("font_weight", 700, 100, 900),
        ):
            try:
                number = int(raw_style.get(key, default))
            except (TypeError, ValueError):
                number = default
            style[key] = str(max(minimum, min(maximum, number)))
        style["outline_color"] = str(raw_style.get("outline_color") or "#000000")
        style["border_color"] = str(raw_style.get("border_color") or "#000000")
        style["container_color"] = str(raw_style.get("container_color") or "")
        style["parent_id"] = str(raw_style.get("parent_id") or "")
        shape = str(raw_style.get("shape") or "rectangle")
        style["shape"] = (
            shape
            if shape
            in {
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
            else "rectangle"
        )
        fill_mode = str(raw_style.get("fill_mode") or "solid")
        style["fill_mode"] = (
            fill_mode
            if fill_mode
            in {
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
            else "solid"
        )
        style["gradient_color_2"] = str(
            raw_style.get("gradient_color_2") or raw_style.get("background_color") or "#111827"
        )
        gradient_mode = str(raw_style.get("gradient_mode") or "none")
        style["gradient_mode"] = (
            gradient_mode
            if gradient_mode in {"none", "bottom", "top", "left", "right", "tint"}
            else "none"
        )
        style["gradient_color"] = str(
            raw_style.get("gradient_color") or "#000000"
        )
        try:
            gradient_opacity = int(raw_style.get("gradient_opacity", 65))
        except (TypeError, ValueError):
            gradient_opacity = 65
        style["gradient_opacity"] = str(max(0, min(100, gradient_opacity)))
        for key in ("overlay_x", "overlay_y", "overlay_width", "overlay_height"):
            raw_number = raw_style.get(key)
            if raw_number in (None, ""):
                style[key] = ""
                continue
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                style[key] = ""
                continue
            minimum = 20 if key in {"overlay_width", "overlay_height"} else 0
            style[key] = str(max(minimum, min(1000, number)))
        alignment = str(raw_style.get("alignment") or "center")
        style["alignment"] = alignment if alignment in {"left", "center", "right"} else "center"
        result[str(field_id)] = style
    return result
