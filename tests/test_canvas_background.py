import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from app.dialogs import ExportOptions
from app.exporter import export_preview
from app.main_window import CanvasBackgroundDialog, MainWindow
from app.models.project import Project
from app.project_manager import ProjectManager
from app.widgets.preview_widget import PreviewWidget


class CanvasBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "background.png"
        source = QImage(100, 200, QImage.Format.Format_RGB32)
        source.fill(QColor("red"))
        painter = QPainter(source)
        painter.fillRect(QRect(0, 100, 100, 100), QColor("blue"))
        painter.end()
        self.assertTrue(source.save(str(self.path)))
        self.project = Project.sample()
        self.project.opening_animation = "stagger_bottom"
        self.project.canvas_background_color = "#00ff00"
        self.preview = PreviewWidget()
        self.preview.set_project(self.project)
        self.widgets = [self.preview]

    def tearDown(self):
        for widget in self.widgets:
            if isinstance(widget, MainWindow):
                widget.pause_playback()
            widget.hide()
            widget.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_project_round_trip_and_legacy_defaults(self):
        legacy = Project.from_dict({"style": {"canvas_background_color": "#123456"}})
        self.assertEqual(legacy.canvas_background_color, "#123456")
        self.assertEqual(legacy.canvas_background_image, "")
        self.assertEqual(legacy.canvas_background_fit, "cover")
        for fit in ("cover", "contain", "stretch"):
            self.project.canvas_background_image = str(self.path)
            self.project.canvas_background_fit = fit
            saved_path = ProjectManager.save(self.project, Path(self.directory.name) / "project")
            loaded = ProjectManager.load(saved_path)
            self.assertEqual(loaded.canvas_background_color, "#00ff00")
            self.assertEqual(loaded.canvas_background_image, str(self.path))
            self.assertEqual(loaded.canvas_background_fit, fit)
        self.assertEqual(
            Project.from_dict({"style": {"canvas_background_fit": "invalid"}}).canvas_background_fit,
            "cover",
        )

    def test_color_fills_opening_frame_and_stays_behind_boxes(self):
        start = self.preview.render_frame(0)
        for x, y in ((0, 0), (1919, 1079), (960, 540)):
            self.assertEqual(start.pixelColor(x, y), QColor("lime"))
        middle = self.preview.render_frame(self.project.item_fixed_duration / 2)
        self.assertEqual(middle.pixelColor(100, 10), QColor("lime"))
        self.assertNotEqual(middle.pixelColor(100, 1000), QColor("lime"))
        for item in self.project.comparison_items:
            item.set_fields([{"id": "name", "type": "name", "value": "", "role": "name"}])
        settled = self.preview.render_frame(self.project.item_fixed_duration)
        self.assertEqual(settled.pixelColor(100, 10), QColor(self.project.name_background_color))

    def test_image_fit_and_png_export_use_canvas_background(self):
        self.project.canvas_background_image = str(self.path)
        for fit in ("cover", "contain", "stretch"):
            with self.subTest(fit=fit):
                self.project.canvas_background_fit = fit
                frame = self.preview.render_frame(0)
                self.assertEqual(frame.pixelColor(960, 100), QColor("red"))
                self.assertEqual(frame.pixelColor(960, 1000), QColor("blue"))
                self.assertEqual(
                    frame.pixelColor(10, 10), QColor("lime" if fit == "contain" else "red")
                )
        output = Path(self.directory.name) / "export.png"
        options = ExportOptions(output, "png", 1920, 1080, 30, 1)
        self.assertTrue(export_preview(self.preview, options, 0))
        exported = QImage(str(output))
        self.assertEqual(exported.size(), QSize(1920, 1080))
        self.assertEqual(exported.convertToFormat(frame.format()), frame)

    def test_missing_or_invalid_image_falls_back_to_color(self):
        invalid = Path(self.directory.name) / "invalid.png"
        invalid.touch()
        for path in (invalid, Path(self.directory.name) / "missing.png"):
            self.project.canvas_background_image = str(path)
            frame = self.preview.render_frame(0)
            self.assertEqual(frame.pixelColor(960, 540), QColor("lime"))
            self.assertEqual(frame.pixelColor(10, 10), QColor("lime"))

    def test_upload_remove_and_cancel_are_staged(self):
        dialog = CanvasBackgroundDialog(self.project, 0)
        self.widgets.append(dialog)
        before = self.project.to_dict()
        self.assertFalse(dialog.remove_button.isEnabled())
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(self.path), "")):
            dialog.choose_button.click()
        dialog.color_button.set_color("#ffffff")
        dialog.fit_combo.setCurrentIndex(dialog.fit_combo.findData("contain"))
        self.assertTrue(dialog.remove_button.isEnabled())
        self.assertTrue(dialog.fit_combo.isEnabled())
        self.assertEqual(dialog.preview.render_frame(0).pixelColor(10, 10), QColor("white"))
        self.assertEqual(self.project.to_dict(), before)
        dialog.remove_button.click()
        self.assertEqual(dialog.preview.render_frame(0).pixelColor(960, 540), QColor("white"))
        self.assertFalse(dialog.fit_combo.isEnabled())
        dialog.reject()
        self.assertEqual(self.project.to_dict(), before)

    def test_upload_cancel_and_invalid_image_preserve_existing_image(self):
        dialog = CanvasBackgroundDialog(self.project, 0)
        self.widgets.append(dialog)
        dialog.image_edit.setText(str(self.path))
        with patch.object(QFileDialog, "getOpenFileName", return_value=("", "")):
            dialog.choose_button.click()
        self.assertEqual(dialog.image_edit.text(), str(self.path))
        with patch.object(QFileDialog, "getOpenFileName", return_value=("missing.png", "")), patch.object(
            QMessageBox, "warning"
        ) as warning:
            dialog.choose_button.click()
            warning.assert_called_once()
        self.assertEqual(dialog.image_edit.text(), str(self.path))

    def test_toolbar_apply_and_cancel_preserve_other_project_settings(self):
        window = MainWindow()
        self.widgets.append(window)
        window.project = self.project
        window._refresh_all()
        before = self.project.to_dict()

        def edit_dialog(dialog):
            dialog.color_button.set_color("#ffffff")
            dialog.image_edit.setText(str(self.path))
            dialog.fit_combo.setCurrentIndex(dialog.fit_combo.findData("contain"))
            return QDialog.DialogCode.Rejected

        with patch.object(CanvasBackgroundDialog, "exec", edit_dialog):
            window.transport.background_button.click()
        self.assertEqual(self.project.to_dict(), before)

        def apply_dialog(dialog):
            edit_dialog(dialog)
            return QDialog.DialogCode.Accepted

        with patch.object(CanvasBackgroundDialog, "exec", apply_dialog):
            window.transport.background_button.click()
        after = self.project.to_dict()
        for key in ("canvas_background_color", "canvas_background_image", "canvas_background_fit"):
            before["style"][key] = after["style"][key]
        self.assertEqual(after, before)
        self.assertEqual(self.project.canvas_background_image, str(self.path))
        self.assertEqual(window.preview.render_frame(0).pixelColor(10, 10), QColor("white"))


if __name__ == "__main__":
    unittest.main()
