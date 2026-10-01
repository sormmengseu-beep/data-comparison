from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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

from app.settings import ROOT_DIR, SUPPORTED_TEXT_FILTER


ITEM_FIELDS = ("name", "rank", "category", "value", "image_path")


def parse_text_items(text: str, format_name: str = "Auto") -> list[dict[str, str]]:
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
        return [_normalized_item(row) for row in payload if isinstance(row, dict)]

    if selected == "lines":
        return [
            {"name": line.strip(), "rank": "", "category": "", "value": "", "image_path": ""}
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
                return parse_text_items(source, "Lines")

    rows = list(csv.reader(io.StringIO(source), delimiter=delimiter))
    rows = [[cell.strip() for cell in row] for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        raise ValueError("No rows were found.")

    header = [cell.casefold().replace(" ", "_") for cell in rows[0]]
    aliases = {"image": "image_path", "imagepath": "image_path", "title": "name"}
    header = [aliases.get(value, value) for value in header]
    has_header = "name" in header and any(value in ITEM_FIELDS for value in header)
    data_rows = rows[1:] if has_header else rows
    fields = header if has_header else list(ITEM_FIELDS)
    result = []
    for row in data_rows:
        mapped = {field: row[index] for index, field in enumerate(fields) if index < len(row)}
        result.append(_normalized_item(mapped))
    return result


def _normalized_item(row: dict) -> dict[str, str]:
    item = {field: str(row.get(field, "") or "").strip() for field in ITEM_FIELDS}
    if not item["name"]:
        item["name"] = "Untitled Item"
    return item


class TextImportDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import Text Data")
        self.resize(680, 520)
        self._items: list[dict[str, str]] = []

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
        self.text_edit.setPlaceholderText(
            "name,rank,category,value,image_path\nArsenal,10th,NET WORTH,$2.6 billion,"
        )
        layout.addWidget(self.text_edit, 1)

        self.summary_label = QLabel("0 rows ready")
        layout.addWidget(self.summary_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Import Items")
        layout.addWidget(buttons)

        upload_button.clicked.connect(self._upload_file)
        self.text_edit.textChanged.connect(self._update_summary)
        self.format_combo.currentTextChanged.connect(self._update_summary)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

    def imported_items(self) -> list[dict[str, str]]:
        return self._items

    def replaces_items(self) -> bool:
        return self.mode_combo.currentIndex() == 1

    def accept(self) -> None:
        try:
            self._items = parse_text_items(
                self.text_edit.toPlainText(), self.format_combo.currentText()
            )
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

    def _update_summary(self) -> None:
        try:
            count = len(
                parse_text_items(self.text_edit.toPlainText(), self.format_combo.currentText())
            )
            self.summary_label.setText(f"{count} row{'s' if count != 1 else ''} ready")
        except ValueError:
            self.summary_label.setText("0 rows ready")


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
        self.resolution_combo.addItem("Full HD - 1920 x 1080", (1920, 1080))
        self.resolution_combo.addItem("HD - 1280 x 720", (1280, 720))
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
