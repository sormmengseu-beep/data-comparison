import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from app.exporter import ExportError
from app.main_window import MainWindow


class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "screenshot.png"
        self.window = MainWindow()

    def tearDown(self):
        self.window.pause_playback()
        self.window.hide()
        self.window.deleteLater()
        self.app.processEvents()
        self.directory.cleanup()

    def test_button_saves_clean_full_resolution_current_frame(self):
        source = Path(self.directory.name) / "source.png"
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        image.fill(QColor("red"))
        self.assertTrue(image.save(str(source)))
        self.window.project.comparison_items[0].set_image_path(str(source))
        self.window._refresh_all()
        self.window.preview.resize(640, 360)
        self.window.set_current_time(1.25)
        selected = self.window.preview._selected_id
        expected = self.window.preview.render_frame(1.25)
        project_before = self.window.project.to_dict()
        self.window.toggle_playback()

        def accept_dialog(dialog):
            self.assertFalse(self.window.playing)
            self.assertFalse(self.window.playback_timer.isActive())
            self.assertEqual(dialog.acceptMode(), QFileDialog.AcceptMode.AcceptSave)
            self.assertEqual(dialog.defaultSuffix(), "png")
            return QDialog.DialogCode.Accepted

        with patch.object(QFileDialog, "exec", accept_dialog), patch.object(
            QFileDialog, "selectedFiles", return_value=[str(self.path)]
        ):
            self.window.transport.screenshot_button.click()

        saved = QImage(str(self.path))
        self.assertFalse(saved.isNull())
        self.assertEqual(saved.size(), QSize(1920, 1080))
        self.assertEqual(saved.convertToFormat(expected.format()), expected)
        self.assertEqual(self.window.current_time, 1.25)
        self.assertEqual(self.window.preview._selected_id, selected)
        self.assertEqual(self.window.project.to_dict(), project_before)
        self.assertIn(str(self.path), self.window.statusBar().currentMessage())

    def test_cancel_does_not_export(self):
        with patch.object(QFileDialog, "exec", return_value=QDialog.DialogCode.Rejected), patch(
            "app.main_window.export_preview"
        ) as export:
            self.window.transport.screenshot_button.click()
        export.assert_not_called()
        self.assertFalse(self.path.exists())

    def test_save_failure_reports_error(self):
        for error in (ExportError("PNG write failed"), OSError("Access denied")):
            with self.subTest(error=error), patch.object(
                QFileDialog, "exec", return_value=QDialog.DialogCode.Accepted
            ), patch.object(QFileDialog, "selectedFiles", return_value=[str(self.path)]), patch(
                "app.main_window.export_preview", side_effect=error
            ), patch.object(self.window, "_warning") as warning:
                self.window.transport.screenshot_button.click()
                warning.assert_called_once_with(str(error))
            self.assertFalse(self.path.exists())
            self.assertNotIn("Screenshot saved:", self.window.statusBar().currentMessage())


if __name__ == "__main__":
    unittest.main()
