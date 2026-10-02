import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from app.dialogs import TextImportDialog, import_columns, parse_text_items
from app.main_window import BoxStylePreview, MainWindow
from app.models.comparison_item import ComparisonItem
from app.models.project import Project


def custom_schema():
    return [
        {"id": "year", "type": "number", "label": "Name", "value": "2007", "role": "rank"},
        {"id": "photo", "type": "image", "label": "Image", "value": "", "role": "image"},
        {"id": "model", "type": "name", "label": "Model", "value": "iPhone", "role": "name"},
        {"id": "battery", "type": "number", "label": "Battery", "value": "1400 mAh", "role": "value"},
        {"id": "decoration", "type": "shape", "label": "Star", "value": "star", "role": ""},
    ]


class TextImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_legacy_import_remains_available(self):
        row = parse_text_items("name,rank,category,value,image_path\nArsenal,10th,NET WORTH,$2.6 billion,")[0]
        self.assertEqual(row["name"], "Arsenal")
        self.assertEqual(row["value"], "$2.6 billion")

    def test_custom_columns_map_to_field_ids_with_or_without_header(self):
        schema = custom_schema()
        self.assertEqual(import_columns(schema), [("year", "name"), ("model", "model"), ("battery", "battery")])
        for source in ("name,model,battery\n2007,iPhone,1400 mAh", "2007,iPhone,1400 mAh"):
            with self.subTest(source=source):
                row = parse_text_items(source, "CSV", schema)[0]
                self.assertEqual((row["year"], row["model"], row["battery"]), ("2007", "iPhone", "1400 mAh"))
                self.assertEqual(row["name"], "2007")

    def test_json_tsv_and_lines_use_custom_columns(self):
        schema = custom_schema()
        sources = [
            ('[{"Name": "2007", "Model": "iPhone", "Battery": "1400 mAh"}]', "JSON"),
            ("name\tmodel\tbattery\n2007\tiPhone\t1400 mAh", "TSV"),
        ]
        for source, format_name in sources:
            self.assertEqual(parse_text_items(source, format_name, schema)[0]["battery"], "1400 mAh")
        self.assertEqual(parse_text_items("2007\n2008", "Lines", schema)[1]["year"], "2008")

    def test_duplicate_labels_and_title_label_are_importable(self):
        schema = custom_schema()
        schema[0]["label"] = "Title"
        schema[2]["label"] = "Battery"
        row = parse_text_items("title,battery,battery_2\n2007,iPhone,1400 mAh", "CSV", schema)[0]
        self.assertEqual((row["year"], row["model"], row["battery"]), ("2007", "iPhone", "1400 mAh"))

    def test_auto_handles_a_single_custom_column_header(self):
        schema = custom_schema()[:2]
        rows = parse_text_items("name\n2007\n2008", "Auto", schema)
        self.assertEqual([row["year"] for row in rows], ["2007", "2008"])

    def test_legacy_headers_work_with_default_box_schema(self):
        schema = ComparisonItem(name="Example").display_fields()
        row = parse_text_items("title,rank,category,value,imagepath\nArsenal,10th,NET WORTH,$2.6 billion,arsenal.png", "CSV", schema)[0]
        self.assertEqual(row["field_name"], "Arsenal")
        self.assertEqual(row["field_image"], "arsenal.png")

    def test_name_label_is_kept_when_schema_is_reapplied(self):
        item = ComparisonItem(name="Original", custom_fields=custom_schema())
        item.set_fields(item.display_fields())
        restored = ComparisonItem.from_dict(item.to_dict())
        restored.set_fields(restored.display_fields())
        self.assertEqual(restored.name, "2007")

    def test_placeholder_changes_with_format_and_omits_image_columns(self):
        dialog = TextImportDialog(schema=custom_schema())
        self.assertTrue(dialog.text_edit.placeholderText().startswith("name,model,battery\n"))
        self.assertEqual(list(dialog.image_folder_edits), ["photo"])
        dialog.format_combo.setCurrentText("JSON")
        self.assertIn('"battery":', dialog.text_edit.placeholderText())
        dialog.format_combo.setCurrentText("TSV")
        self.assertTrue(dialog.text_edit.placeholderText().startswith("name\tmodel\tbattery\n"))
        dialog.deleteLater()

    def test_folder_matches_filenames_before_assigning_remaining_images(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("1.png", "2.png", "10.png", "iPhone 4.PNG", "notes.txt"):
                (folder / name).touch()
            dialog = TextImportDialog(schema=custom_schema())
            dialog.image_folder_edits["photo"].setText(directory)
            dialog.text_edit.setPlainText("2007,Other,1400 mAh\n2010,iPhone 4,1420 mAh\n2008,Other 2,1500 mAh")
            rows = dialog._parse_items()
            self.assertEqual([Path(row["photo"]).name for row in rows], ["1.png", "iPhone 4.PNG", "2.png"])
            self.assertEqual(rows[1]["image_path"], rows[1]["photo"])
            self.assertIn("3/3 images", dialog.summary_label.text())
            dialog.deleteLater()

    def test_multiple_image_blocks_have_independent_folders_and_missing_images(self):
        schema = custom_schema()
        schema.append({"id": "back", "type": "image", "label": "Back", "value": "", "role": ""})
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            front = folder / "front"
            back = folder / "back"
            front.mkdir()
            back.mkdir()
            (front / "2007.png").touch()
            (back / "2007.jpg").touch()
            dialog = TextImportDialog(schema=schema)
            dialog.image_folder_edits["photo"].setText(str(front))
            dialog.image_folder_edits["back"].setText(str(back))
            dialog.text_edit.setPlainText("2007,iPhone,1400 mAh\n2008,iPhone 3G,1500 mAh")
            rows = dialog._parse_items()
            self.assertEqual(Path(rows[0]["back"]).name, "2007.jpg")
            self.assertEqual(rows[1]["photo"], "")
            self.assertIn("2/4 images", dialog.summary_label.text())
            dialog.deleteLater()

    def test_invalid_folder_reports_error(self):
        with tempfile.TemporaryDirectory() as directory:
            dialog = TextImportDialog(schema=custom_schema())
            dialog.image_folder_edits["photo"].setText(str(Path(directory) / "missing"))
            dialog.text_edit.setPlainText("2007,iPhone,1400 mAh")
            with self.assertRaisesRegex(ValueError, "Image folder not found"):
                dialog._parse_items()
            self.assertIn("Image folder not found", dialog.summary_label.text())
            dialog.deleteLater()

    def test_visual_order_includes_free_moves_and_image_children(self):
        item = ComparisonItem(name="Example", custom_fields=custom_schema())
        preview = BoxStylePreview(item)
        preview.resize(640, 1080)
        preview.field_styles = {
            "year": {"overlay_x": "0", "overlay_y": "60", "overlay_width": "1000", "overlay_height": "50"},
            "battery": {"overlay_x": "0", "overlay_y": "0", "overlay_width": "1000", "overlay_height": "50"},
            "model": {"parent_id": "photo", "overlay_x": "0", "overlay_y": "100", "overlay_width": "1000", "overlay_height": "100"},
        }
        ordered = preview.fields_in_visual_order()
        self.assertEqual(ordered[0]["id"], "battery")
        self.assertEqual(len(ordered), len(custom_schema()))
        self.assertLess([field["id"] for field in ordered].index("model"), [field["id"] for field in ordered].index("decoration"))
        preview.deleteLater()

    def test_append_and_replace_preserve_custom_layout_and_imported_values(self):
        for replace in (False, True):
            with self.subTest(replace=replace):
                window = MainWindow()
                original = ComparisonItem(name="Original", custom_fields=custom_schema())
                window.project = Project(comparison_items=[original])
                window.selected_item_id = original.id
                window.project.field_styles = {"battery": {"height_weight": "130"}}

                def accept_import(dialog):
                    dialog.text_edit.setPlainText("name,model,battery\n2010,iPhone 4,1420 mAh")
                    dialog.mode_combo.setCurrentIndex(1 if replace else 0)
                    dialog.accept()
                    return QDialog.DialogCode.Accepted

                with patch.object(TextImportDialog, "exec", accept_import):
                    window.add_text()
                item = window.project.comparison_items[-1]
                fields = item.display_fields()
                self.assertEqual([field["id"] for field in fields], [field["id"] for field in custom_schema()])
                self.assertEqual([field["value"] for field in fields], ["2010", "", "iPhone 4", "1420 mAh", "star"])
                self.assertEqual(item.name, "2010")
                self.assertEqual(window.project.field_styles["battery"]["height_weight"], "130")
                self.assertEqual(len(window.project.comparison_items), 1 if replace else 2)
                if not replace:
                    self.assertEqual(original.display_fields(), custom_schema())
                window.deleteLater()


if __name__ == "__main__":
    unittest.main()
