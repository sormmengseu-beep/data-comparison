from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import isfinite
from uuid import uuid4


def new_item_id() -> str:
    return f"item_{uuid4().hex[:8]}"


DEFAULT_FIELD_IDS = {
    "image": "field_image",
    "name": "field_name",
    "category": "field_category",
    "rank": "field_rank",
    "value": "field_value",
}


@dataclass
class ComparisonItem:
    name: str
    rank: str = ""
    category: str = ""
    value: str = ""
    image_path: str = ""
    start_time: float = 0.0
    duration: float = 8.0
    animation: str = "slide_left"
    image_fit: str = ""
    image_crop_x: float = 0.0
    image_crop_y: float = 0.0
    image_height_percent_3: int = 0
    image_height_percent_4: int = 0
    image_height_percent_5: int = 0
    card_border_color: str = ""
    name_background_color: str = ""
    name_text_color: str = ""
    category_background_color: str = ""
    category_text_color: str = ""
    rank_background_color: str = ""
    rank_text_color: str = ""
    value_background_color: str = ""
    value_text_color: str = ""
    custom_fields: list[dict[str, str]] = field(default_factory=list)
    image_transforms: dict[str, dict[str, float | str]] = field(default_factory=dict)
    id: str = field(default_factory=new_item_id)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["start_time"] = float(self.start_time)
        data["duration"] = float(self.duration)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonItem":
        return cls(
            id=str(data.get("id") or new_item_id()),
            name=str(data.get("name") or "Untitled Item"),
            rank=str(data.get("rank") or ""),
            category=str(data.get("category") or ""),
            value=str(data.get("value") or ""),
            image_path=str(data.get("image_path") or ""),
            start_time=max(0.0, float(data.get("start_time") or 0.0)),
            duration=max(0.1, float(data.get("duration") or 0.1)),
            animation=str(data.get("animation") or "slide_left"),
            image_fit=str(data.get("image_fit") or ""),
            image_crop_x=_crop_offset(data.get("image_crop_x")),
            image_crop_y=_crop_offset(data.get("image_crop_y")),
            image_height_percent_3=_height_override(data.get("image_height_percent_3")),
            image_height_percent_4=_height_override(data.get("image_height_percent_4")),
            image_height_percent_5=_height_override(data.get("image_height_percent_5")),
            card_border_color=str(data.get("card_border_color") or ""),
            name_background_color=str(data.get("name_background_color") or ""),
            name_text_color=str(data.get("name_text_color") or ""),
            category_background_color=str(data.get("category_background_color") or ""),
            category_text_color=str(data.get("category_text_color") or ""),
            rank_background_color=str(data.get("rank_background_color") or ""),
            rank_text_color=str(data.get("rank_text_color") or ""),
            value_background_color=str(data.get("value_background_color") or ""),
            value_text_color=str(data.get("value_text_color") or ""),
            custom_fields=_normalized_fields(data.get("custom_fields")),
            image_transforms=_image_transforms(data.get("image_transforms")),
        )

    def display_fields(self) -> list[dict[str, str]]:
        if self.custom_fields:
            return [dict(field_data) for field_data in self.custom_fields]
        return [
            _field("image", "Image", self.image_path, "image"),
            _field("name", "Name", self.name, "name"),
            _field("text", "Category", self.category, "category"),
            _field("number", "Rank / Score", self.rank, "rank"),
            _field("number", "Value", self.value, "value"),
        ]

    def set_fields(self, fields: list[dict[str, str]]) -> None:
        old_images = {
            field_data["id"]: field_data["value"]
            for field_data in self.display_fields() if field_data["type"] == "image"
        }
        self.custom_fields = _normalized_fields(fields)
        image_fields = [field for field in self.custom_fields if field["type"] == "image"]
        unchanged_images = {
            field_data["id"] for field_data in image_fields
            if old_images.get(field_data["id"]) == field_data["value"]
        }
        self.image_transforms = {
            field_id: transform for field_id, transform in self.image_transforms.items()
            if field_id in unchanged_images
        }
        self.image_path = image_fields[0]["value"] if image_fields else ""
        for field_data in self.custom_fields:
            value = field_data["value"]
            role = field_data.get("role", "")
            if field_data["type"] == "name" and value:
                self.name = value
            elif role == "category":
                self.category = value
            elif role == "rank":
                self.rank = value
            elif role == "value":
                self.value = value

    def set_image_path(self, path: str) -> None:
        fields = self.display_fields()
        for field_data in fields:
            if field_data["type"] == "image":
                field_data["value"] = path
                self.set_fields(fields)
                return
        fields.insert(0, _field("image", "Image", path, "image"))
        self.set_fields(fields)


def normalize_image_transform(value: object) -> dict[str, float | str]:
    raw = value if isinstance(value, dict) else {}
    result: dict[str, float | str] = {}
    fit = str(raw.get("fit") or "")
    if fit in {"cover", "contain", "stretch"}:
        result["fit"] = fit
    for key, default, minimum, maximum in (
        ("scale_x", 1.0, 0.1, 5.0),
        ("scale_y", 1.0, 0.1, 5.0),
        ("offset_x", 0.0, -5.0, 5.0),
        ("offset_y", 0.0, -5.0, 5.0),
    ):
        try:
            number = float(raw.get(key, default))
            result[key] = max(minimum, min(maximum, number)) if isfinite(number) else default
        except (TypeError, ValueError):
            result[key] = default
    return result


def _image_transforms(value: object) -> dict[str, dict[str, float | str]]:
    if not isinstance(value, dict):
        return {}
    return {
        str(field_id): normalize_image_transform(transform)
        for field_id, transform in value.items() if isinstance(transform, dict)
    }


def _height_override(value: object) -> int:
    if value in (None, "", 0, "0"):
        return 0
    return max(35, min(75, int(value)))


def _crop_offset(value: object) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _field(field_type: str, label: str, value: str, role: str = "") -> dict[str, str]:
    return {
        "id": DEFAULT_FIELD_IDS.get(role, f"field_{uuid4().hex[:8]}"),
        "type": field_type,
        "label": label,
        "value": value,
        "role": role,
    }


def _normalized_fields(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    valid_types = {"name", "text", "number", "image", "shape"}
    result = []
    for raw_field in value:
        if not isinstance(raw_field, dict):
            continue
        field_type = str(raw_field.get("type") or "text").lower()
        if field_type not in valid_types:
            field_type = "text"
        result.append(
            {
                "id": str(raw_field.get("id") or f"field_{uuid4().hex[:8]}"),
                "type": field_type,
                "label": str(raw_field.get("label") or field_type.title()),
                "value": str(raw_field.get("value") or ""),
                "role": str(raw_field.get("role") or ""),
            }
        )
    return result
