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
        empty.accept()
        self.assertNotEqual(empty.result(), QDialog.DialogCode.Accepted)

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
            QTest.mouseClick(dialog.box_preview, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
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
