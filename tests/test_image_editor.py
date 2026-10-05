import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox

from app.dialogs import ExportOptions, ImageEditorDialog
from app.exporter import export_preview
from app.main_window import BoxCustomizationDialog, MainWindow
from app.models.comparison_item import ComparisonItem, normalize_image_transform
from app.models.project import Project
from app.utils.image_utils import (
    ImageCache,
    draw_image,
    image_field_frame_size,
    image_target_rect,
)
from app.widgets.preview_widget import PreviewWidget


class ImageEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "source.png")
        image = QImage(200, 200, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))
        painter = QPainter(image)
        painter.fillRect(QRect(100, 0, 100, 200), QColor("blue"))
        painter.end()
        image.save(self.path)
        self.project = Project.sample()
        self.item = self.project.comparison_items[0]
        self.item.set_image_path(self.path)
        self.field_id = self.item.display_fields()[0]["id"]
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            widget.hide()
            widget.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def editor(self):
        editor = ImageEditorDialog(self.path, QSize(400, 400), "contain")
        self.widgets.append(editor)
        editor.show()
        self.app.processEvents()
        return editor

    def test_resize_handles_and_drag(self):
        editor = self.editor()
        canvas = editor.canvas
        self.assertEqual(len(canvas._handles()), 8)
        top_left = canvas.image_rect().topLeft()
        handle = canvas._handles()[4].toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=handle)
        QTest.mouseMove(canvas, handle + QPoint(35, 25))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=handle + QPoint(35, 25))
        self.assertGreater(float(canvas.transform["scale_x"]), 1)
        self.assertAlmostEqual(float(canvas.transform["scale_x"]), float(canvas.transform["scale_y"]))
        self.assertAlmostEqual(canvas.image_rect().left(), top_left.x())
        self.assertAlmostEqual(canvas.image_rect().top(), top_left.y())
        before = dict(canvas.transform)
        center = canvas._screen_rect(canvas.image_rect()).center().toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(canvas, center + QPoint(25, 20))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=center + QPoint(25, 20))
        self.assertGreater(float(canvas.transform["offset_x"]), float(before["offset_x"]))
        self.assertGreater(float(canvas.transform["offset_y"]), float(before["offset_y"]))
        editor.aspect_check.setChecked(False)
        height = canvas.image_rect().height()
        handle = canvas._handles()[3].toPoint()
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=handle)
        QTest.mouseMove(canvas, handle + QPoint(30, 0))
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=handle + QPoint(30, 0))
        self.assertAlmostEqual(canvas.image_rect().height(), height)

    def test_controls_reset_and_empty_image(self):
        editor = self.editor()
        editor.width_spin.setValue(150)
        self.assertEqual(editor.height_spin.value(), 150)
        editor.aspect_check.setChecked(False)
        editor.height_spin.setValue(75)
        self.assertEqual(editor.width_spin.value(), 150)
        editor.fit_combo.setCurrentIndex(editor.fit_combo.findData("cover"))
        self.assertEqual(editor.image_transform()["fit"], "cover")
        editor._reset()
        self.assertEqual(editor.image_transform(), normalize_image_transform({"fit": "contain"}))
        empty = ImageEditorDialog("", QSize(400, 400))
        self.widgets.append(empty)
        self.assertFalse(empty.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled())
        self.assertFalse(empty.apply_all_button.isEnabled())
        empty._accept_all_boxes()
        self.assertFalse(empty.apply_to_all_boxes)
        empty.accept()
        self.assertNotEqual(empty.result(), QDialog.DialogCode.Accepted)

    def test_apply_all_button_accepts_current_transform(self):
        editor = self.editor()
        editor.canvas.set_transform(
            {
                "fit": "contain", "scale_x": 1.5, "scale_y": 0.8,
                "offset_x": 0.2, "offset_y": -0.1,
            }
        )
        expected = editor.image_transform()
        self.assertFalse(editor.apply_to_all_boxes)
        self.assertTrue(editor.apply_all_button.isEnabled())
        QTest.mouseClick(editor.apply_all_button, Qt.MouseButton.LeftButton)
        self.assertEqual(editor.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(editor.apply_to_all_boxes)
        self.assertEqual(editor.image_transform(), expected)

    def prepare_image_slots(self):
        other_path = str(Path(self.directory.name) / "other.png")
        QImage(self.path).save(other_path)
        for index, item in enumerate(self.project.comparison_items):
            fields = item.display_fields()[:2]
            fields.append(
                {
                    "id": "second_image", "type": "image", "label": "Second image",
                    "value": self.path if index == 0 else (other_path if index == 1 else ""),
                }
            )
            item.set_fields(fields)
            item.image_transforms[self.field_id] = normalize_image_transform({"offset_x": -0.2})
        return other_path

    def test_main_window_apply_all_copies_image_to_third_slot_only(self):
        other_path = self.prepare_image_slots()
        window = MainWindow()
        self.widgets.append(window)
        window.project = self.project
        window.selected_item_id = self.item.id
        window._refresh_all()
        original_images = [item.display_fields() for item in self.project.comparison_items]
        original_primary = [
            dict(item.image_transforms[self.field_id])
            for item in self.project.comparison_items
        ]
        expected = normalize_image_transform(
            {
                "fit": "contain", "scale_x": 1.5, "scale_y": 0.8,
                "offset_x": 0.2, "offset_y": -0.1,
            }
        )

        def accepted(editor):
            editor.image_path = other_path
            editor.canvas.set_transform(expected)
            editor._accept_all_boxes()
            return editor.result()

        with patch.object(ImageEditorDialog, "exec", accepted):
            window.open_image_editor(self.item.id, "second_image")
        for index, item in enumerate(self.project.comparison_items):
            self.assertEqual(item.image_transforms["second_image"], expected)
            self.assertEqual(item.image_transforms[self.field_id], original_primary[index])
            second = next(
                field for field in item.display_fields() if field["id"] == "second_image"
            )
            self.assertEqual(second["value"], other_path)
            self.assertEqual(item.display_fields()[2]["id"], "second_image")
            self.assertEqual(item.display_fields()[:2], original_images[index][:2])
        window.preview.set_selected_item("")
        window.preview.set_current_time(self.project.item_fixed_duration)
        frame = window.preview._render_canvas().toImage()
        regions = [
            rect.adjusted(2, 2, -2, -2)
            for rect, _item_id, field_id in window.preview._image_regions
            if field_id == "second_image"
        ]
        self.assertEqual(len(regions), 3)
        for region in regions[1:]:
            self.assertEqual(frame.copy(region), frame.copy(regions[0]))
        restored = Project.from_dict(json.loads(json.dumps(self.project.to_dict())))
        for item in restored.comparison_items:
            self.assertEqual(item.image_transforms["second_image"], expected)
            self.assertEqual(item.display_fields()[2]["value"], other_path)
        self.item.image_transforms["second_image"]["offset_x"] = 0.5
        self.assertEqual(
            self.project.comparison_items[1].image_transforms["second_image"]["offset_x"],
            0.2,
        )

    def test_designer_apply_all_stages_changes_until_final_apply(self):
        self.prepare_image_slots()
        original = self.project.to_dict()
        expected = normalize_image_transform(
            {
                "fit": "stretch", "scale_x": 1.5, "scale_y": 0.8,
                "offset_x": 0.2, "offset_y": -0.1,
            }
        )

        def accepted(editor):
            editor.canvas.set_transform(expected)
            editor._accept_all_boxes()
            return editor.result()

        cancelled = BoxCustomizationDialog(self.project, self.item)
        self.widgets.append(cancelled)
        with patch.object(ImageEditorDialog, "exec", accepted):
            cancelled._edit_image("second_image")
        self.assertEqual(self.project.to_dict(), original)
        cancelled.reject()
        self.assertEqual(self.project.to_dict(), original)

        dialog = BoxCustomizationDialog(self.project, self.item)
        self.widgets.append(dialog)
        with patch.object(ImageEditorDialog, "exec", accepted):
            dialog._edit_image("second_image")
        self.assertEqual(self.project.to_dict(), original)
        dialog.apply_changes()
        for item in self.project.comparison_items:
            self.assertEqual(item.image_transforms["second_image"], expected)
            self.assertEqual(item.image_transforms[self.field_id]["offset_x"], -0.2)
            self.assertEqual(item.display_fields()[2]["value"], self.path)

    def test_single_image_edit_after_apply_all_remains_local(self):
        other_path = self.prepare_image_slots()
        dialog = BoxCustomizationDialog(self.project, self.item)
        self.widgets.append(dialog)

        def apply_all(editor):
            editor.width_spin.setValue(150)
            editor._accept_all_boxes()
            return editor.result()

        def apply_single(editor):
            editor.image_path = other_path
            editor.width_spin.setValue(75)
            editor.accept()
            return editor.result()

        with patch.object(ImageEditorDialog, "exec", apply_all):
            dialog._edit_image("second_image")
        with patch.object(ImageEditorDialog, "exec", apply_single):
            dialog._edit_image("second_image")
        dialog.apply_changes()
        self.assertEqual(self.item.image_transforms["second_image"]["scale_x"], 0.75)
        self.assertEqual(self.item.display_fields()[2]["value"], other_path)
        for item in self.project.comparison_items[1:]:
            self.assertEqual(item.image_transforms["second_image"]["scale_x"], 1.5)
            self.assertEqual(item.display_fields()[2]["value"], self.path)

    def test_geometry_and_clipping(self):
        frame = QRectF(0, 0, 200, 100)
        cover = image_target_rect(QSize(100, 100), frame, "cover")
        self.assertEqual(cover, QRectF(0, -50, 200, 200))
        contain = image_target_rect(QSize(100, 100), frame, "contain")
        self.assertEqual(contain, QRectF(50, 0, 100, 100))
        target = image_target_rect(QSize(100, 100), frame, "contain",
                                  {"scale_x": 2, "scale_y": 2, "offset_x": 0.25})
        self.assertEqual(target, QRectF(50, -50, 200, 200))
        image = QImage(240, 180, QImage.Format.Format_RGB32)
        image.fill(QColor("green"))
        painter = QPainter(image)
        draw_image(painter, ImageCache(), self.path, QRect(20, 20, 200, 100),
                   "cover", {"scale_x": 4, "scale_y": 4})
        painter.end()
        self.assertEqual(image.pixelColor(100, 121), QColor("green"))
        self.assertNotEqual(image.pixelColor(100, 50), QColor("green"))
        free_frame = image_field_frame_size(
            self.item.display_fields(),
            self.field_id,
            {
                self.field_id: {
                    "overlay_x": "100",
                    "overlay_y": "200",
                    "overlay_width": "500",
                    "overlay_height": "400",
                }
            },
            QSize(640, 1080),
            56,
        )
        self.assertEqual(free_frame, QSize(320, 432))

    def test_transparent_image_pixels_reveal_existing_background(self):
        transparent_path = str(Path(self.directory.name) / "transparent.png")
        source = QImage(40, 40, QImage.Format.Format_ARGB32)
        source.fill(Qt.GlobalColor.transparent)
        painter = QPainter(source)
        painter.fillRect(QRect(12, 12, 16, 16), QColor("red"))
        painter.end()
        self.assertTrue(source.save(transparent_path))

        target = QImage(80, 80, QImage.Format.Format_RGB32)
        target.fill(QColor("green"))
        painter = QPainter(target)
        draw_image(
            painter,
            ImageCache(),
            transparent_path,
            QRect(0, 0, 80, 80),
            "stretch",
        )
        painter.end()

        self.assertEqual(target.pixelColor(5, 5), QColor("green"))
        self.assertEqual(target.pixelColor(40, 40), QColor("red"))

    def test_persistence_replacement_and_field_isolation(self):
        self.item.image_transforms[self.field_id] = {"scale_x": 1.5, "offset_x": 0.2, "fit": "contain"}
        restored = Project.from_dict(json.loads(json.dumps(self.project.to_dict())))
        values = restored.comparison_items[0].image_transforms[self.field_id]
        self.assertEqual(values["scale_x"], 1.5)
        self.assertEqual(values["offset_x"], 0.2)
        self.assertEqual(values["fit"], "contain")
        self.assertEqual(restored.comparison_items[1].image_transforms, {})
        self.item.set_fields(list(reversed(self.item.display_fields())))
        self.assertIn(self.field_id, self.item.image_transforms)
        self.item.set_image_path("replacement.png")
        self.assertEqual(self.item.image_transforms, {})
        self.assertEqual(ComparisonItem.from_dict({"name": "Old project"}).image_transforms, {})
        self.assertEqual(normalize_image_transform({"scale_x": "bad", "offset_y": float("nan")}),
                         normalize_image_transform({}))

    def test_click_targets_during_scroll_and_after_export(self):
        preview = PreviewWidget()
        self.widgets.append(preview)
        preview.resize(1000, 700)
        # Include more cards than the three-column viewport so this test
        # exercises click targeting after an actual scroll.
        self.project.comparison_items.append(ComparisonItem(name="Extra item"))
        self.project.apply_fixed_item_timing()
        preview.set_project(self.project)
        preview.show()
        self.app.processEvents()
        received = []
        preview.image_edit_requested.connect(lambda *args: received.append(args))
        area = preview._preview_rect()
        point = QPoint(area.x() + area.width() // 6, area.y() + area.height() // 5)
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(received[-1], (self.item.id, self.field_id))
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton,
                         pos=QPoint(point.x(), area.y() + area.height() - 10))
        self.assertEqual(len(received), 1)
        preview.set_current_time(self.project.item_fixed_duration * 2)
        self.app.processEvents()
        preview.render_frame(0)
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(received[-1][0], self.project.comparison_items[1].id)
        fields = self.item.display_fields()
        fields.insert(1, {"id": "second_image", "type": "image", "value": self.path, "label": "Second"})
        self.item.set_fields(fields)
        preview.set_current_time(0)
        self.app.processEvents()
        QTest.mouseClick(preview, Qt.MouseButton.LeftButton,
                         pos=QPoint(point.x(), area.y() + int(area.height() * 0.4)))
        self.assertEqual(received[-1], (self.item.id, "second_image"))

    def test_customize_stages_apply_and_cancel(self):
        dialog = BoxCustomizationDialog(self.project, self.item)
        self.widgets.append(dialog)
        dialog.show()
        self.app.processEvents()
        dialog.field_styles[self.field_id].update(
            {
                "overlay_x": "0",
                "overlay_y": "0",
                "overlay_width": "500",
                "overlay_height": "500",
            }
        )
        dialog._update_preview()
        self.app.processEvents()
        def accepted(editor):
            self.assertEqual(editor.canvas.frame.size().toSize(), QSize(320, 540))
            editor.width_spin.setValue(150)
            return QDialog.DialogCode.Accepted
        with patch.object(ImageEditorDialog, "exec", accepted):
            QTest.mouseDClick(dialog.box_preview, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
        self.assertEqual(self.item.image_transforms, {})
        self.assertEqual(dialog.box_preview.item.image_transforms[self.field_id]["scale_x"], 1.5)
        dialog.reject()
        self.assertEqual(self.item.image_transforms, {})
        dialog.apply_changes()
        self.assertEqual(self.item.image_transforms[self.field_id]["scale_x"], 1.5)
        self.assertEqual(self.project.comparison_items[1].image_transforms, {})

    def test_main_window_apply_cancel_and_export(self):
        window = MainWindow()
        self.widgets.append(window)
        self.project.field_styles[self.field_id] = {
            "overlay_x": "0",
            "overlay_y": "0",
            "overlay_width": "500",
            "overlay_height": "500",
        }
        window.project = self.project
        window.selected_item_id = self.item.id
        window._refresh_all()
        original = self.item.to_dict()
        with patch.object(ImageEditorDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            window.open_image_editor(self.item.id, self.field_id)
        self.assertEqual(self.item.to_dict(), original)
        before = window.preview.render_frame(0)
        def accepted(editor):
            self.assertEqual(editor.canvas.frame.size().toSize(), QSize(320, 540))
            editor.width_spin.setValue(50)
            return QDialog.DialogCode.Accepted
        with patch.object(ImageEditorDialog, "exec", accepted):
            window.open_image_editor(self.item.id, self.field_id)
        self.assertEqual(self.item.image_transforms[self.field_id]["scale_x"], 0.5)
        after = window.preview.render_frame(0)
        self.assertNotEqual(before, after)
        path = Path(self.directory.name) / "export.png"
        options = ExportOptions(path, "png", 1920, 1080, 30, 1)
        self.assertTrue(export_preview(window.preview, options, 0))
        exported = QImage(str(path)).convertToFormat(after.format())
        self.assertEqual(exported, after)


if __name__ == "__main__":
    unittest.main()
