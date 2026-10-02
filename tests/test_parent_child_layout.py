import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.main_window import BoxCustomizationDialog
from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.widgets.preview_widget import PreviewWidget


class ParentChildLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hierarchy_is_applied_to_every_box_and_persisted(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        fields = dialog._image_item.display_fields()
        image_id = next(str(field["id"]) for field in fields if field["type"] == "image")
        child_id = next(str(field["id"]) for field in fields if field["type"] != "image")

        dialog._hierarchy_drop_requested(child_id, image_id, True, image_id)
        dialog.field_styles[image_id].update(
            {
                "gradient_mode": "bottom",
                "gradient_color": "#123456",
                "gradient_opacity": "72",
            }
        )
        dialog.apply_changes()
        dialog.deleteLater()

        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.field_styles[child_id]["parent_id"], image_id)
        self.assertEqual(restored.field_styles[image_id]["gradient_mode"], "bottom")
        self.assertEqual(restored.field_styles[image_id]["gradient_opacity"], "72")
        for item in restored.comparison_items:
            self.assertIn(child_id, {str(field["id"]) for field in item.display_fields()})

    def test_parent_image_fills_card_and_gradient_is_rendered(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = str(Path(directory) / "red.png")
            source = QImage(200, 200, QImage.Format.Format_RGB32)
            source.fill(QColor("#ff0000"))
            source.save(image_path)

            item = ComparisonItem(name="Overlay")
            item.set_fields(
                [
                    {
                        "id": "background_image",
                        "type": "image",
                        "label": "Background",
                        "value": image_path,
                        "role": "image",
                    },
                    {
                        "id": "overlay_text",
                        "type": "text",
                        "label": "Overlay",
                        "value": "",
                        "role": "category",
                    },
                ]
            )
            project = Project(comparison_items=[item])
            project.field_styles = {
                "background_image": {
                    "height_weight": "100",
                    "gradient_mode": "bottom",
                    "gradient_color": "#000000",
                    "gradient_opacity": "100",
                },
                "overlay_text": {
                    "parent_id": "background_image",
                    "background_color": "#000000",
                    "text_color": "#ffffff",
                    "height_weight": "100",
                },
            }
            project.apply_fixed_item_timing()
            preview = PreviewWidget()
            preview.set_project(project)
            frame = preview.render_frame(project.item_fixed_duration)
            top = frame.pixelColor(320, 120)
            bottom = frame.pixelColor(320, 960)
            self.assertGreater(top.red(), bottom.red())
            self.assertGreater(top.red(), 100)
            self.assertLess(bottom.red(), 80)
            preview.deleteLater()


if __name__ == "__main__":
    unittest.main()
