import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow, ProjectSettingsDialog
from app.dialogs import ExportOptions
from app.exporter import export_preview
from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.project_manager import ProjectManager
from app.settings import CANVAS_HEIGHT, CANVAS_WIDTH, OPENING_ANIMATION_OPTIONS
from app.widgets.preview_widget import PreviewWidget


class OpeningAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.preview = PreviewWidget()
        self.project = Project(
            comparison_items=[ComparisonItem(name=f"Item {i}") for i in range(7)]
        )
        # Solid bands make the moving cards and empty canvas easy to distinguish.
        for item in self.project.comparison_items:
            item.set_fields([
                {"id": "field_name", "type": "name", "value": "", "role": "name"}
            ])
        self.project.apply_fixed_item_timing()
        self.preview.set_project(self.project)
        self.widgets = [self.preview]

    def tearDown(self):
        for widget in self.widgets:
            widget.hide()
            widget.deleteLater()
        self.app.processEvents()

    def test_vertical_opening_for_each_layout_and_direction(self):
        background = QColor(self.project.canvas_background_color)
        card_color = QColor(self.project.name_background_color)
        duration = self.project.item_fixed_duration
        for columns in (3, 4, 5):
            self.project.preview_max_columns = columns
            for mode in ("from_bottom", "from_top"):
                with self.subTest(columns=columns, mode=mode):
                    self.project.opening_animation = mode
                    start = self.preview.render_frame(0)
                    middle = self.preview.render_frame(duration / 2)
                    settled = self.preview.render_frame(duration)
                    for index in range(columns):
                        x = int((index + 0.5) * CANVAS_WIDTH / columns)
                        self.assertEqual(start.pixelColor(x, CANVAS_HEIGHT // 2), background)
                        # At half time the ease-out motion has nearly reached its slot.
                        empty_y = 30 if mode == "from_bottom" else CANVAS_HEIGHT - 30
                        filled_y = CANVAS_HEIGHT - 30 if mode == "from_bottom" else 30
                        self.assertEqual(middle.pixelColor(x, empty_y), background)
                        self.assertEqual(middle.pixelColor(x, filled_y), card_color)
                        self.assertEqual(settled.pixelColor(x, empty_y), card_color)

    def test_default_and_later_horizontal_scroll_are_unchanged(self):
        duration = self.project.item_fixed_duration
        for columns in (3, 4, 5):
            self.project.preview_max_columns = columns
            self.project.opening_animation = "slide_left"
            default_start = self.preview.render_frame(0)
            self.assertEqual(default_start, self.preview.render_frame(duration))
            later_times = (duration, duration * 1.5, duration * 3, self.project.total_duration())
            expected = [self.preview.render_frame(time) for time in later_times]
            for _, mode in OPENING_ANIMATION_OPTIONS:
                self.project.opening_animation = mode
                for time, frame in zip(later_times, expected):
                    with self.subTest(columns=columns, mode=mode, time=time):
                        self.assertEqual(self.preview.render_frame(time), frame)

    def test_ending_holds_the_last_full_layout(self):
        background = QColor(self.project.canvas_background_color)
        for columns in (3, 4, 5):
            for item_count in (1, 2, columns, columns + 2):
                items = [ComparisonItem(name=f"Item {index}") for index in range(item_count)]
                for index, item in enumerate(items):
                    field_id = f"ending_{index}"
                    item.set_fields([
                        {"id": field_id, "type": "name", "value": "", "role": "name"}
                    ])
                    self.project.field_styles[field_id] = {
                        "background_color": "#00ff00" if index == item_count - 1 else "#ff0000"
                    }
                self.project.comparison_items = items
                self.project.preview_max_columns = columns
                self.project.apply_fixed_item_timing()
                end = self.project.total_duration()
                for mode in ("slide_left", "reveal_left", "stagger_bottom"):
                    with self.subTest(columns=columns, item_count=item_count, mode=mode):
                        self.project.opening_animation = mode
                        frame = self.preview.render_frame(end)
                        card_width = CANVAS_WIDTH // columns
                        visible_count = min(columns, item_count)
                        for slot in range(columns):
                            color = frame.pixelColor(slot * card_width + 30, 30)
                            if slot >= visible_count:
                                self.assertEqual(color, background)
                            elif slot == visible_count - 1:
                                self.assertEqual(color, QColor("lime"))
                            else:
                                self.assertEqual(color, QColor("red"))
                        for seconds in (end + 0.5, end + self.project.item_fixed_duration * 10):
                            self.assertEqual(self.preview.render_frame(seconds), frame)

    def test_scroll_continues_through_last_group_then_holds_in_export(self):
        duration = self.project.item_fixed_duration
        self.preview.set_current_time(duration * 5.5)
        self.assertAlmostEqual(self.preview._slide_offset_units(7), 4.0)
        self.preview.set_current_time(duration * 6.5)
        self.assertAlmostEqual(self.preview._slide_offset_units(7), 4.0)
        end = self.project.total_duration()
        frame = self.preview.render_frame(end)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ending.png"
            options = ExportOptions(path, "png", CANVAS_WIDTH, CANVAS_HEIGHT, 30, end + duration)
            self.assertTrue(export_preview(self.preview, options, end + duration))
            exported = QImage(str(path)).convertToFormat(frame.format())
            self.assertEqual(exported, frame)
        self.project.comparison_items.clear()
        self.preview.set_current_time(end + duration)
        self.assertEqual(self.preview._slide_offset_units(0), 0)

    def test_new_styles_have_an_entrance_and_repeatable_frames(self):
        background = QColor(self.project.canvas_background_color)
        duration = self.project.item_fixed_duration
        for columns in (3, 4, 5):
            self.project.preview_max_columns = columns
            self.project.opening_animation = "slide_left"
            reference = self.preview.render_frame(0)
            for _, mode in OPENING_ANIMATION_OPTIONS[3:]:
                with self.subTest(columns=columns, mode=mode):
                    self.project.opening_animation = mode
                    start = self.preview.render_frame(0)
                    for index in range(columns):
                        x = int((index + 0.5) * CANVAS_WIDTH / columns)
                        self.assertEqual(start.pixelColor(x, CANVAS_HEIGHT // 2), background)
                    first = self.preview.render_frame(duration * 0.15)
                    middle = self.preview.render_frame(duration * 0.5)
                    self.assertNotEqual(first, start)
                    self.assertNotEqual(first, reference)
                    self.assertNotEqual(first, middle)
                    self.assertEqual(self.preview.render_frame(duration * 0.15), first)

    def test_staggered_and_alternating_directions(self):
        duration = self.project.item_fixed_duration
        color = QColor(self.project.name_background_color)
        background = QColor(self.project.canvas_background_color)
        for columns in (3, 4, 5):
            self.project.preview_max_columns = columns
            first_x = CANVAS_WIDTH // columns // 2
            last_x = int((columns - 0.5) * CANVAS_WIDTH / columns)
            for mode, edge in (("stagger_bottom", CANVAS_HEIGHT - 30), ("stagger_top", 30)):
                self.project.opening_animation = mode
                frame = self.preview.render_frame(duration * 0.15)
                self.assertEqual(frame.pixelColor(first_x, edge), color)
                self.assertEqual(frame.pixelColor(last_x, edge), background)
            self.project.opening_animation = "alternating"
            frame = self.preview.render_frame(duration * 0.4)
            for index in range(columns):
                x = int((index + 0.5) * CANVAS_WIDTH / columns)
                empty_y = 30 if index % 2 == 0 else CANVAS_HEIGHT - 30
                filled_y = CANVAS_HEIGHT - 30 if index % 2 == 0 else 30
                self.assertEqual(frame.pixelColor(x, empty_y), background)
                self.assertEqual(frame.pixelColor(x, filled_y), color)

    def test_image_click_targets_follow_zoom_and_reveal(self):
        self.project = Project.sample()
        self.preview.set_project(self.project)
        self.preview.resize(1000, 600)

        def screen_point(x, y):
            area = self.preview._preview_rect()
            return QPoint(
                area.x() + round(x * area.width() / CANVAS_WIDTH),
                area.y() + round(y * area.height() / CANVAS_HEIGHT),
            )

        for mode in ("zoom_in", "pop_in", "reveal_left"):
            self.project.opening_animation = mode
            self.preview.set_current_time(0)
            self.preview._render_canvas()
            self.assertEqual(self.preview._image_regions, [])
            self.preview.set_current_time(self.project.item_fixed_duration * 0.1)
            self.preview._render_canvas()
            regions = self.preview._image_regions
            self.assertTrue(regions)
            for region, item_id, field_id in regions:
                self.assertEqual(
                    self.preview._image_at(screen_point(region.center().x(), region.center().y())),
                    (item_id, field_id),
                )
            if mode in {"zoom_in", "pop_in"}:
                self.assertGreater(regions[0][0].left(), 0)
                self.assertIsNone(self.preview._image_at(screen_point(10, 10)))
            else:
                self.assertIsNone(self.preview._image_at(screen_point(1000, 100)))

    def test_saved_projects_and_legacy_default(self):
        with tempfile.TemporaryDirectory() as directory:
            for _, mode in OPENING_ANIMATION_OPTIONS:
                self.project.opening_animation = mode
                path = ProjectManager.save(self.project, Path(directory) / mode)
                self.assertEqual(ProjectManager.load(path).opening_animation, mode)
        legacy = self.project.to_dict()
        legacy.pop("opening_animation")
        self.assertEqual(Project.from_dict(legacy).opening_animation, "slide_left")
        legacy["opening_animation"] = "unknown"
        self.assertEqual(Project.from_dict(legacy).opening_animation, "slide_left")

    def test_controls_update_project_and_restore_without_emitting(self):
        window = MainWindow()
        self.widgets.append(window)
        combo = window.transport.opening_animation_combo
        self.assertEqual(combo.currentData(), "slide_left")
        combo.setCurrentIndex(combo.findData("from_bottom"))
        self.assertEqual(window.project.opening_animation, "from_bottom")
        self.assertEqual(window.preview._project.opening_animation, "from_bottom")
        dialog = ProjectSettingsDialog(window.project)
        self.widgets.append(dialog)
        self.assertEqual(dialog.opening_animation_combo.currentData(), "from_bottom")
        dialog.opening_animation_combo.setCurrentIndex(
            dialog.opening_animation_combo.findData("from_top")
        )
        dialog.apply_to(window.project)
        changes = []
        window.transport.opening_animation_changed.connect(changes.append)
        window._refresh_all()
        self.assertEqual(combo.currentData(), "from_top")
        self.assertEqual(changes, [])
        window.set_preview_columns(5)
        self.assertEqual(window.project.opening_animation, "from_top")


if __name__ == "__main__":
    unittest.main()
