from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.settings import (
    PROJECT_RESOLUTION_PRESETS,
    ROOT_DIR,
    SUPPORTED_IMAGE_FILTER,
    SUPPORTED_TEXT_FILTER,
)
from app.models.comparison_item import normalize_image_transform
from app.widgets.image_editor import ImageEditorCanvas
from app.utils.icons import IconButton


class ImageEditorDialog(QDialog):
    def __init__(self, path: str, frame_size: QSize, fit: str = "cover",
                 transform: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Image")
        self.resize(800, 650)
        self.image_path = path
        self.apply_to_all_boxes = False
        self._default_fit = fit
        self._updating = False
        values = normalize_image_transform(transform)
        values.setdefault("fit", fit)
        layout = QVBoxLayout(self)
        title = QLabel("Drag the image to move it. Drag a white handle to resize it.")
        title.setWordWrap(True)
        layout.addWidget(title)
        self.canvas = ImageEditorCanvas(frame_size, fit, values)
        layout.addWidget(self.canvas, 1)
        controls = QHBoxLayout()
        self.choose_button = QPushButton("Choose Image")
        self.fit_combo = QComboBox()
        for label, mode in (("Cover", "cover"), ("Contain", "contain"), ("Stretch", "stretch")):
            self.fit_combo.addItem(label, mode)
        self.width_spin = QDoubleSpinBox()
        self.height_spin = QDoubleSpinBox()
        for spin in (self.width_spin, self.height_spin):
            spin.setRange(10, 500)
            spin.setDecimals(1)
            spin.setSuffix(" %")
            spin.setSingleStep(5)
        self.aspect_check = QCheckBox("Lock proportions")
        self.aspect_check.setChecked(True)
        self.reset_button = QPushButton("Reset")
        controls.addWidget(self.choose_button)
        controls.addWidget(self.fit_combo)
        controls.addWidget(QLabel("Width"))
        controls.addWidget(self.width_spin)
        controls.addWidget(QLabel("Height"))
        controls.addWidget(self.height_spin)
        layout.addLayout(controls)
        options = QHBoxLayout()
        options.addWidget(self.aspect_check)
        options.addStretch(1)
        options.addWidget(self.reset_button)
        layout.addLayout(options)
        layout.addWidget(QLabel("Dashed outline: image area in the box. Areas outside it are cropped."))
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        self.apply_all_button = self.buttons.addButton(
            "Apply to All Boxes", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.apply_all_button.setToolTip(
            "Copy this image, its position, size, and fit to the same slot in every box"
        )
        layout.addWidget(self.buttons)
        self.choose_button.clicked.connect(self._choose_image)
        self.fit_combo.currentIndexChanged.connect(self._change_fit)
        self.width_spin.valueChanged.connect(lambda value: self._change_size("scale_x", value))
        self.height_spin.valueChanged.connect(lambda value: self._change_size("scale_y", value))
        self.aspect_check.toggled.connect(lambda checked: setattr(self.canvas, "keep_aspect", checked))
        self.reset_button.clicked.connect(self._reset)
        self.canvas.transform_changed.connect(self._sync_controls)
        self.buttons.accepted.connect(self.accept)
        self.apply_all_button.clicked.connect(self._accept_all_boxes)
        self.buttons.rejected.connect(self.reject)
        self._load_image()
        self._sync_controls()

    def image_transform(self) -> dict[str, float | str]:
        return dict(self.canvas.transform)

    def _load_image(self) -> None:
        pixmap = QPixmap(self.image_path) if self.image_path else QPixmap()
        self.canvas.set_image(pixmap)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.canvas.has_image)
        self.apply_all_button.setEnabled(self.canvas.has_image)
        for widget in (self.fit_combo, self.width_spin, self.height_spin, self.reset_button):
            widget.setEnabled(self.canvas.has_image)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Image", str(Path.home()), SUPPORTED_IMAGE_FILTER
        )
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "Choose Image", "This image could not be opened.")
            return
        self.image_path = path
        self._load_image()
        self._reset()

    def _sync_controls(self, *_args) -> None:
        self._updating = True
        values = self.canvas.transform
        self.fit_combo.setCurrentIndex(self.fit_combo.findData(values.get("fit", self._default_fit)))
        self.width_spin.setValue(float(values["scale_x"]) * 100)
        self.height_spin.setValue(float(values["scale_y"]) * 100)
        self._updating = False

    def _change_size(self, key: str, percent: float) -> None:
        if self._updating:
            return
        values = self.image_transform()
        ratio = percent / 100 / float(values[key])
        if self.aspect_check.isChecked():
            other = "scale_y" if key == "scale_x" else "scale_x"
            ratio = max(0.1 / float(values[other]), min(5 / float(values[other]), ratio))
            values[other] = float(values[other]) * ratio
        values[key] = float(values[key]) * ratio
        self.canvas.set_transform(values)
        self._sync_controls()

    def _change_fit(self) -> None:
        if self._updating:
            return
        values = self.image_transform()
        values["fit"] = str(self.fit_combo.currentData())
        self.canvas.set_transform(values)

    def _reset(self) -> None:
        self.canvas.set_transform({"fit": self._default_fit})
        self._sync_controls()

    def _accept_all_boxes(self) -> None:
        if self.canvas.has_image:
            self.apply_to_all_boxes = True
            self.accept()

    def accept(self) -> None:
        if self.canvas.has_image:
            super().accept()


ITEM_FIELDS = ("name", "rank", "category", "value", "image_path")


def _column_key(value: str) -> str:
    return value.strip().casefold().replace(" ", "_")


def import_columns(fields: list[dict[str, str]]) -> list[tuple[str, str]]:
    columns = []
    used: set[str] = set()
    for field in fields:
        if field.get("type") == "image":
            continue
        label = str(field.get("label") or "Text").strip()
        base_name = _column_key(label)
        name = base_name
        suffix = 2
        while _column_key(name) in used:
            name = f"{base_name}_{suffix}"
            suffix += 1
        used.add(_column_key(name))
        columns.append((str(field["id"]), name))
    return columns


def parse_text_items(
    text: str,
    format_name: str = "Auto",
    schema: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    source = text.strip()
    if not source:
        raise ValueError("Add or upload some text first.")

    selected = format_name.casefold()
    if selected == "json" or (selected == "auto" and source[:1] in "[{"):
        try:
            payload = json.loads(source)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg}.") from exc
        if isinstance(payload, dict):
            payload = payload.get("items", [payload])
        if not isinstance(payload, list):
            raise ValueError("JSON must contain an item or a list of items.")
        lookup = _schema_column_lookup(schema) if schema is not None else {}
        return [
            _normalized_item(
                {lookup.get(_column_key(str(key)), str(key)): value for key, value in row.items()}
                if schema is not None else row,
                schema,
            )
            for row in payload if isinstance(row, dict)
        ]

    if selected == "lines":
        columns = import_columns(schema) if schema is not None else []
        first_column = columns[0][0] if columns else "name"
        return [
            _normalized_item({first_column: line.strip()}, schema)
            for line in source.splitlines()
            if line.strip()
        ]

    delimiter = "\t" if selected == "tsv" else ","
    if selected == "auto":
        sample = source[:4096]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            if all(separator not in sample for separator in (",", "\t", ";", "|")):
                return parse_text_items(source, "CSV" if schema is not None else "Lines", schema)

    rows = list(csv.reader(io.StringIO(source), delimiter=delimiter))
    rows = [[cell.strip() for cell in row] for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("No rows were found.")

    header = [_column_key(cell) for cell in rows[0]]
    aliases = {"image": "image_path", "imagepath": "image_path", "title": "name"}
    if schema is not None:
        lookup = _schema_column_lookup(schema)
        has_header = any(value in lookup for value in header) and all(
            not value or value in lookup for value in header
        )
        fields = [lookup.get(value, value) for value in header] if has_header else [
            field_id for field_id, _label in import_columns(schema)
        ]
    else:
        header = [aliases.get(value, value) for value in header]
        has_header = "name" in header and any(value in ITEM_FIELDS for value in header)
        fields = header if has_header else list(ITEM_FIELDS)
    data_rows = rows[1:] if has_header else rows
    result = []
    for row in data_rows:
        mapped = {field: row[index] for index, field in enumerate(fields) if index < len(row)}
        result.append(_normalized_item(mapped, schema))
    return result


def _schema_column_lookup(schema: list[dict[str, str]]) -> dict[str, str]:
    lookup = {}
    for field in schema:
        field_id = str(field["id"])
        lookup[_column_key(field_id)] = field_id
        role = str(field.get("role") or "")
        if role:
            lookup.setdefault(_column_key(role), field_id)
    for field_id, label in import_columns(schema):
        lookup[_column_key(label)] = field_id
    image = next((field for field in schema if field.get("type") == "image"), None)
    if image:
        lookup["image_path"] = str(image["id"])
        lookup.setdefault("image", str(image["id"]))
        lookup.setdefault("imagepath", str(image["id"]))
    if "name" in lookup:
        lookup.setdefault("title", lookup["name"])
    return lookup


def _normalized_item(
    row: dict, schema: list[dict[str, str]] | None = None
) -> dict[str, str]:
    item = {field: str(row.get(field, "") or "").strip() for field in ITEM_FIELDS}
    if schema is not None:
        for field in schema:
            field_id = str(field["id"])
            item[field_id] = str(row.get(field_id, "") or "").strip()
            role = str(field.get("role") or "")
            if role in ITEM_FIELDS:
                item["image_path" if field.get("type") == "image" else role] = item[field_id]
        name_field = next(
            (field for field in schema if field.get("type") not in {"image", "shape"}
             and _column_key(field.get("label", "")) == "name"),
            None,
        )
        if name_field is None:
            name_field = next((field for field in schema if field.get("type") == "name"), None)
        columns = import_columns(schema)
        name_id = str(name_field["id"]) if name_field else columns[0][0] if columns else ""
        item["name"] = item.get(name_id, "")
    if not item["name"]:
        item["name"] = "Untitled Item"
    return item


class TextImportDialog(QDialog):
    def __init__(
        self, parent: QWidget | None = None,
        schema: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Text Data")
        self.resize(680, 520)
        self._items: list[dict[str, str]] = []
        self.schema = [dict(field) for field in schema] if schema is not None else None
        self.image_folder_edits: dict[str, QLineEdit] = {}
        self._image_file_cache: dict[str, list[Path]] = {}

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Auto", "CSV", "TSV", "JSON", "Lines"])
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Append to project", "Replace all items"])
        upload_button = QPushButton("Upload File")
        top.addWidget(QLabel("Format"))
        top.addWidget(self.format_combo)
        top.addSpacing(12)
        top.addWidget(QLabel("Import mode"))
        top.addWidget(self.mode_combo)
        top.addStretch(1)
        top.addWidget(upload_button)
        layout.addLayout(top)

        self.text_edit = QPlainTextEdit()
        self.columns_label = QLabel()
        self.columns_label.setWordWrap(True)
        layout.addWidget(self.columns_label)
        layout.addWidget(self.text_edit, 1)

        image_form = QFormLayout()
        for field in self.schema or []:
            if field.get("type") != "image":
                continue
            field_id = str(field["id"])
            folder_row = QWidget()
            folder_layout = QHBoxLayout(folder_row)
            folder_layout.setContentsMargins(0, 0, 0, 0)
            folder_edit = QLineEdit()
            folder_edit.setPlaceholderText("Image folder (optional)")
            folder_edit.setToolTip("Match filenames to text values; otherwise use file order.")
            browse_button = IconButton("file", "Choose image folder")
            folder_layout.addWidget(folder_edit, 1)
            folder_layout.addWidget(browse_button)
            image_form.addRow(f"{field.get('label') or 'Image'} folder", folder_row)
            self.image_folder_edits[field_id] = folder_edit
            browse_button.clicked.connect(
                lambda _checked=False, edit=folder_edit: self._choose_image_folder(edit)
            )
            folder_edit.textChanged.connect(self._update_summary)
        layout.addLayout(image_form)

        self.summary_label = QLabel("0 rows ready")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import Items")
        layout.addWidget(buttons)

        upload_button.clicked.connect(self._upload_file)
        self.text_edit.textChanged.connect(self._update_summary)
        self.format_combo.currentTextChanged.connect(self._format_changed)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._format_changed()

    def imported_items(self) -> list[dict[str, str]]:
        return self._items

    def replaces_items(self) -> bool:
        return self.mode_combo.currentIndex() == 1

    def accept(self) -> None:
        try:
            self._image_file_cache.clear()
            self._items = self._parse_items()
        except ValueError as exc:
            QMessageBox.warning(self, "Import Text Data", str(exc))
            return
        if not self._items:
            QMessageBox.warning(self, "Import Text Data", "No valid items were found.")
            return
        super().accept()

    def _upload_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Upload Text Data", str(Path.home()), SUPPORTED_TEXT_FILTER
        )
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, "Import Text Data", f"Unable to read the file: {exc}")
            return
        self.text_edit.setPlainText(text)
        suffix = Path(path).suffix.lower()
        format_by_suffix = {".csv": "CSV", ".tsv": "TSV", ".json": "JSON"}
        if suffix in format_by_suffix:
            self.format_combo.setCurrentText(format_by_suffix[suffix])

    def _format_changed(self) -> None:
        columns = import_columns(self.schema) if self.schema is not None else [
            (field, field) for field in ITEM_FIELDS
        ]
        labels = [label for _field_id, label in columns]
        values_by_id = {
            str(field["id"]): str(field.get("value") or "") for field in self.schema or []
        }
        values = [values_by_id.get(field_id) or "..." for field_id, _label in columns]
        if self.schema is None:
            values = ["Arsenal", "10th", "NET WORTH", "$2.6 billion", ""]
        selected = self.format_combo.currentText()
        self.columns_label.setText("Columns: " + ", ".join(labels))
        if selected == "JSON":
            placeholder = json.dumps([dict(zip(labels, values))], indent=2)
        elif selected == "Lines":
            placeholder = "\n".join([values[0], "..."]) if values else ""
            self.columns_label.setText("Columns: " + (labels[0] if labels else ""))
        else:
            output = io.StringIO()
            writer = csv.writer(
                output, delimiter="\t" if selected == "TSV" else ",", lineterminator="\n"
            )
            writer.writerows([labels, values])
            placeholder = output.getvalue().rstrip()
        self.text_edit.setPlaceholderText(placeholder)
        self._update_summary()

    def _choose_image_folder(self, edit: QLineEdit) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Choose Image Folder", edit.text() or str(Path.home())
        )
        if path:
            self._image_file_cache.clear()
            edit.setText(path)

    def _parse_items(self) -> list[dict[str, str]]:
        items = parse_text_items(
            self.text_edit.toPlainText(), self.format_combo.currentText(), self.schema
        )
        text_ids = [field_id for field_id, _label in import_columns(self.schema or [])]
        for field in self.schema or []:
            if field.get("type") != "image":
                continue
            field_id = str(field["id"])
            folder_text = self.image_folder_edits[field_id].text().strip()
            if not folder_text:
                for item in items:
                    item[field_id] = item[field_id] or str(field.get("value") or "")
                continue
            folder = Path(folder_text).expanduser()
            if not folder.is_dir():
                raise ValueError(f"Image folder not found: {folder_text}")
            if folder_text not in self._image_file_cache:
                try:
                    self._image_file_cache[folder_text] = sorted(
                        (path for path in folder.iterdir() if path.is_file()
                         and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}),
                        key=lambda path: [
                            part.zfill(20) if part.isdigit() else part.casefold()
                            for part in re.split(r"(\d+)", path.name)
                        ],
                    )
                except OSError as exc:
                    raise ValueError(f"Unable to read image folder: {exc}") from exc
            files = self._image_file_cache[folder_text]
            if not files:
                raise ValueError(f"No supported images found in: {folder_text}")
            by_name = {self._image_name(path.stem): path for path in files}
            by_path = {str(path.resolve()): path for path in files}
            used: set[Path] = set()
            pending = []
            for item in items:
                if item[field_id]:
                    explicit = by_path.get(str(Path(item[field_id]).expanduser().resolve()))
                    if explicit is not None:
                        used.add(explicit)
                    continue
                candidates = [item["name"]] + [item.get(key, "") for key in text_ids]
                match = next(
                    (by_name[self._image_name(value)] for value in candidates
                     if value and self._image_name(value) in by_name),
                    None,
                )
                if match is None:
                    pending.append(item)
                else:
                    item[field_id] = str(match.resolve())
                    used.add(match)
            remaining = iter(path for path in files if path not in used)
            for item in pending:
                path = next(remaining, None)
                item[field_id] = str(path.resolve()) if path else ""
        first_image = next(
            (field for field in self.schema or [] if field.get("type") == "image"), None
        )
        if first_image:
            for item in items:
                item["image_path"] = item[str(first_image["id"])]
        return items

    @staticmethod
    def _image_name(value: str) -> str:
        return "".join(character for character in value.casefold() if character.isalnum())

    def _update_summary(self) -> None:
        try:
            items = self._parse_items()
            count = len(items)
            summary = f"{count} row{'s' if count != 1 else ''} ready"
            if self.image_folder_edits:
                total = count * len(self.image_folder_edits)
                matched = sum(
                    bool(item.get(field_id)) for item in items for field_id in self.image_folder_edits
                )
                summary += f" | {matched}/{total} images"
            self.summary_label.setText(summary)
        except ValueError as exc:
            self.summary_label.setText(str(exc) if self.text_edit.toPlainText().strip() else "0 rows ready")


@dataclass(frozen=True)
class ExportOptions:
    path: Path
    format_name: str
    width: int
    height: int
    fps: int
    duration: float


class ExportDialog(QDialog):
    def __init__(
        self,
        project_name: str,
        project_fps: int,
        project_duration: float,
        content_duration: float,
        parent: QWidget | None = None,
        project_width: int = 1920,
        project_height: int = 1080,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(520)
        self._project_name = project_name
        self._project_duration = project_duration
        self._content_duration = max(0.1, content_duration)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.format_combo = QComboBox()
        self.format_combo.addItem("MP4 video", "mp4")
        self.format_combo.addItem("AVI video", "avi")
        self.format_combo.addItem("PNG current frame", "png")

        self.resolution_combo = QComboBox()
        project_size = (int(project_width), int(project_height))
        self.resolution_combo.addItem(
            f"Project - {project_size[0]} x {project_size[1]}", project_size
        )
        for label, width, height in PROJECT_RESOLUTION_PRESETS:
            size = (width, height)
            if size != project_size:
                self.resolution_combo.addItem(f"{label} - {width} x {height}", size)
        self.resolution_combo.addItem("Preview - 960 x 540", (960, 540))

        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "60"])
        self.fps_combo.setCurrentText(str(project_fps if project_fps in (30, 60) else 30))

        self.duration_combo = QComboBox()
        self.duration_combo.addItem(f"All items - {self._content_duration:.2f}s", self._content_duration)
        if abs(project_duration - self._content_duration) > 0.001:
            self.duration_combo.addItem(f"Full project - {project_duration:.2f}s", project_duration)

        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        self.path_edit = QLineEdit()
        browse_button = QPushButton("Browse")
        path_layout.addWidget(self.path_edit, 1)
        path_layout.addWidget(browse_button)

        form.addRow("Format", self.format_combo)
        form.addRow("Resolution", self.resolution_combo)
        form.addRow("Frame rate", self.fps_combo)
        form.addRow("Duration", self.duration_combo)
        form.addRow("Save to", path_row)
        layout.addLayout(form)

        self.estimate_label = QLabel()
        self.estimate_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.estimate_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("PrimaryButton")
        layout.addWidget(buttons)

        browse_button.clicked.connect(self._browse)
        self.format_combo.currentIndexChanged.connect(self._format_changed)
        self.fps_combo.currentTextChanged.connect(self._update_estimate)
        self.duration_combo.currentIndexChanged.connect(self._update_estimate)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._format_changed()

    def options(self) -> ExportOptions:
        width, height = self.resolution_combo.currentData()
        return ExportOptions(
            path=Path(self.path_edit.text().strip()),
            format_name=str(self.format_combo.currentData()),
            width=int(width),
            height=int(height),
            fps=int(self.fps_combo.currentText()),
            duration=float(self.duration_combo.currentData()),
        )

    def accept(self) -> None:
        if not self.path_edit.text().strip():
            self._browse()
        if not self.path_edit.text().strip():
            return
        expected_suffix = f".{self.format_combo.currentData()}"
        path = Path(self.path_edit.text().strip())
        if path.suffix.lower() != expected_suffix:
            path = path.with_suffix(expected_suffix)
            self.path_edit.setText(str(path))
        super().accept()

    def _browse(self) -> None:
        format_name = str(self.format_combo.currentData())
        filters = {
            "mp4": "MP4 Video (*.mp4)",
            "avi": "AVI Video (*.avi)",
            "png": "PNG Image (*.png)",
        }
        default_dir = ROOT_DIR / "exports"
        default_name = f"{self._safe_name()}.{format_name}"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export", str(default_dir / default_name), filters[format_name]
        )
        if path:
            self.path_edit.setText(path)

    def _format_changed(self) -> None:
        is_video = self.format_combo.currentData() != "png"
        self.fps_combo.setEnabled(is_video)
        self.duration_combo.setEnabled(is_video)
        current = Path(self.path_edit.text()) if self.path_edit.text().strip() else None
        if current is not None:
            self.path_edit.setText(str(current.with_suffix(f".{self.format_combo.currentData()}")))
        self._update_estimate()

    def _update_estimate(self) -> None:
        if self.format_combo.currentData() == "png":
            self.estimate_label.setText("Current preview frame")
            return
        frames = round(float(self.duration_combo.currentData()) * int(self.fps_combo.currentText()))
        self.estimate_label.setText(f"{frames:,} frames")

    def _safe_name(self) -> str:
        name = "".join(character if character.isalnum() else "_" for character in self._project_name)
        return name.strip("_").lower() or "comparison"
