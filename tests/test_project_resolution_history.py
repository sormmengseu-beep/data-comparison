import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.dialogs import ExportDialog
from app.main_window import MainWindow, ProjectSettingsDialog
from app.models.project import Project
from app.widgets.preview_widget import PreviewWidget


class ProjectResolutionHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.widgets = []

    def tearDown(self):
        for widget in self.widgets:
            if isinstance(widget, MainWindow):
                widget.pause_playback()
            widget.deleteLater()
        self.app.processEvents()

    def test_resolution_presets_and_custom_size_apply_and_persist(self):
        project = Project.sample()
        dialog = ProjectSettingsDialog(project)
        self.widgets.append(dialog)

        preset_index = next(
            index
            for index in range(dialog.resolution_combo.count())
            if dialog.resolution_combo.itemData(index) == (3840, 2160)
        )
        dialog.resolution_combo.setCurrentIndex(preset_index)
        self.assertEqual((dialog.width_spin.value(), dialog.height_spin.value()), (3840, 2160))
        self.assertFalse(dialog.width_spin.isEnabled())
        dialog.apply_to(project)
        self.assertEqual((project.width, project.height), (3840, 2160))

        dialog.resolution_combo.setCurrentIndex(dialog.resolution_combo.count() - 1)
        dialog.width_spin.setValue(2048)
        dialog.height_spin.setValue(1080)
        self.assertTrue(dialog.width_spin.isEnabled())
        dialog.apply_to(project)
        restored = Project.from_dict(project.to_dict())
        self.assertEqual((restored.width, restored.height), (2048, 1080))

    def test_preview_and_export_use_project_resolution(self):
        project = Project.sample()
        project.width = 2560
        project.height = 1440
        preview = PreviewWidget()
        preview.set_project(project)
        self.widgets.append(preview)

        self.assertEqual(preview.render_frame(0).size(), QSize(2560, 1440))
        dialog = ExportDialog(
            project.name,
            project.fps,
            project.total_duration(),
            project.content_duration(),
            project_width=project.width,
            project_height=project.height,
        )
        self.widgets.append(dialog)
        self.assertEqual(dialog.resolution_combo.currentData(), (2560, 1440))

    def test_add_item_can_be_undone_and_redone(self):
        window = MainWindow()
        self.widgets.append(window)
        window.show()
        self.app.processEvents()
        original_ids = [item.id for item in window.project.comparison_items]

        window.add_comparison_item()
        added_ids = [item.id for item in window.project.comparison_items]
        self.assertEqual(len(added_ids), len(original_ids) + 1)
        self.assertTrue(window.undo_action.isEnabled())

        QTest.keyClick(
            window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier
        )
        self.app.processEvents()
        self.assertEqual(
            [item.id for item in window.project.comparison_items], original_ids
        )
        self.assertTrue(window.redo_action.isEnabled())

        QTest.keyClick(
            window, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier
        )
        self.app.processEvents()
        self.assertEqual(
            [item.id for item in window.project.comparison_items], added_ids
        )


if __name__ == "__main__":
    unittest.main()
