import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QSizePolicy,
    QSlider,
)

from app.main_window import BoxCustomizationDialog, BoxStylePreview, ColorButton
from app.models.comparison_item import ComparisonItem
from app.models.project import Project
from app.widgets.preview_widget import PreviewWidget


class ParentChildLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_box_customization_dialog_opens_medium_with_compact_color_buttons(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])

        self.assertFalse(dialog.windowState() & Qt.WindowState.WindowMaximized)
        self.assertFalse(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
        self.assertLessEqual(dialog.width(), 1280)
        self.assertEqual(dialog.border_color_button.minimumWidth(), 124)
        self.assertEqual(dialog.border_color_button.maximumWidth(), 124)
        self.assertEqual(
            dialog.border_color_button.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.Fixed,
        )
        dialog.deleteLater()

    def test_selected_image_hides_unused_text_content_controls(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        fields = dialog._image_item.display_fields()
        image_id = next(str(field["id"]) for field in fields if field["type"] == "image")
        text_id = next(str(field["id"]) for field in fields if field["type"] == "text")

        image_row = next(
            row
            for row in range(dialog.field_order_list.count())
            if dialog.field_order_list.item(row).data(Qt.ItemDataRole.UserRole) == image_id
        )
        dialog.field_order_list.setCurrentRow(image_row)
        self.assertTrue(dialog.field_label_edit.isHidden())
        self.assertTrue(dialog.field_value_edit.isHidden())
        self.assertFalse(dialog.field_browse_button.isHidden())
        self.assertFalse(dialog.image_gradient_combo.isHidden())

        text_row = next(
            row
            for row in range(dialog.field_order_list.count())
            if dialog.field_order_list.item(row).data(Qt.ItemDataRole.UserRole) == text_id
        )
        dialog.field_order_list.setCurrentRow(text_row)
        self.assertFalse(dialog.field_label_edit.isHidden())
        self.assertFalse(dialog.field_value_edit.isHidden())
        self.assertTrue(dialog.field_browse_button.isHidden())
        dialog.deleteLater()

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

    def test_preview_layer_menu_exposes_all_four_order_actions(self):
        item = Project.sample().comparison_items[0]
        preview = BoxStylePreview(item)
        preview.field_styles = {}
        field_ids = [str(field["id"]) for field in item.display_fields()]
        selected_id = field_ids[0]

        requested = []
        preview.layer_order_requested.connect(
            lambda field_id, operation: requested.append((field_id, operation))
        )
        menu = preview._layer_context_menu(selected_id)

        self.assertEqual(
            [action.text() for action in menu.actions()],
            [
                "Bring to Front",
                "Bring Forward",
                "Send Backward",
                "Send to Back",
            ],
        )
        menu.actions()[1].trigger()
        self.assertEqual(requested, [(selected_id, "bring_forward")])
        menu.deleteLater()
        preview.deleteLater()

    def test_layer_actions_reorder_only_siblings(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        fields = dialog._image_item.display_fields()
        image_id = next(str(field["id"]) for field in fields if field["type"] == "image")
        text_ids = [
            str(field["id"]) for field in fields if field["type"] != "image"
        ]
        child_ids = text_ids[:2]
        for child_id in child_ids:
            dialog.field_styles[child_id]["parent_id"] = image_id
        dialog._rebuild_order_list(dialog._ordered_field_ids(), child_ids[0])

        root_before = [
            field_id
            for field_id in dialog._ordered_field_ids()
            if field_id not in child_ids
        ]
        dialog._preview_layer_order_requested(child_ids[0], "bring_to_front")
        child_order = [
            field_id
            for field_id in dialog._ordered_field_ids()
            if field_id in child_ids
        ]
        self.assertEqual(child_order, [child_ids[1], child_ids[0]])
        self.assertEqual(
            [
                field_id
                for field_id in dialog._ordered_field_ids()
                if field_id not in child_ids
            ],
            root_before,
        )
        dialog.apply_changes()
        for item in project.comparison_items:
            persisted_child_order = [
                str(field["id"])
                for field in item.display_fields()
                if str(field["id"]) in child_ids
            ]
            self.assertEqual(persisted_child_order, [child_ids[1], child_ids[0]])

        dialog._preview_layer_order_requested(child_ids[0], "send_to_back")
        child_order = [
            field_id
            for field_id in dialog._ordered_field_ids()
            if field_id in child_ids
        ]
        self.assertEqual(child_order, child_ids)
        dialog.deleteLater()

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
                    "shape": "ellipse",
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
            self.assertEqual(frame.pixelColor(20, 20), QColor(project.canvas_background_color))
            preview.deleteLater()

    def test_all_objects_can_be_freely_moved_and_snapped(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        dialog.show()
        self.app.processEvents()
        preview = dialog.box_preview
        preview.repaint()
        self.app.processEvents()
        region, field_id, _field_type = next(
            entry for entry in preview._field_regions if entry[2] != "image"
        )
        self.assertTrue(
            all(handle.width() == 7 for handle in preview._resize_handles(region).values())
        )
        start = region.center()
        destination = start + QPoint(31, 17)
        QTest.mousePress(preview, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(preview, destination)
        QTest.mouseRelease(preview, Qt.MouseButton.LeftButton, pos=destination)
        style = dialog.field_styles[field_id]
        self.assertNotEqual(style["overlay_x"], "")
        self.assertNotEqual(style["overlay_y"], "")
        self.assertNotEqual(style["overlay_width"], "")
        self.assertNotEqual(style["overlay_height"], "")

        preview._pressed_field_id = field_id
        preview._overlay_interaction = "move"
        preview._field_regions = []
        snapped = preview._snap_rect(
            region.translated(preview.rect().center().x() - region.center().x() + 3, 0),
            preview.rect(),
        )
        self.assertEqual(snapped.center().x(), preview.rect().center().x())
        self.assertIn(("v", preview.rect().center().x()), preview._snap_guides)
        dialog.deleteLater()

    def test_designer_preview_uses_vector_editor_modifier_controls(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        dialog.show()
        self.app.processEvents()
        field_id = dialog._add_content_item("", "rectangle")
        preview = dialog.box_preview
        preview.repaint()
        self.app.processEvents()
        region, _field_id, _field_type = next(
            entry for entry in preview._field_regions if entry[1] == field_id
        )
        parent = preview._overlay_parent_regions[field_id]

        preview._selected_field_id = field_id
        preview.keyPressEvent(type("Event", (), {
            "key": lambda self: Qt.Key.Key_Right,
            "modifiers": lambda self: Qt.KeyboardModifier.ShiftModifier,
            "accept": lambda self: None,
        })())
        self.assertGreater(int(dialog.field_styles[field_id]["overlay_x"]), 0)

        preview._press_position = region.bottomRight()
        preview._pressed_field_id = field_id
        preview._overlay_interaction = "resize"
        preview._resize_handle = "se"
        preview._interaction_rect = QRect(region)
        preview._interaction_parent_rect = QRect(parent)
        preview._update_overlay_geometry(
            region.bottomRight() + QPoint(80, 10),
            Qt.KeyboardModifier.ShiftModifier,
        )
        resized = preview._overlay_rect(
            parent,
            region,
            dialog.field_styles[field_id],
        )
        self.assertAlmostEqual(
            resized.width() / resized.height(),
            region.width() / region.height(),
            delta=0.12,
        )
        dialog.deleteLater()

    def test_designer_preview_fits_available_space_at_box_aspect_ratio(self):
        item = Project.sample().comparison_items[0]
        preview = BoxStylePreview(item, project_height=1080)
        preview.resize(900, 700)
        preview.columns = 3

        canvas = preview._canvas_rect()

        self.assertEqual(canvas.height(), preview.height() - 16)
        self.assertGreater(canvas.width(), 330)
        self.assertAlmostEqual(canvas.width() / canvas.height(), (1920 / 3) / 1080, places=2)
        self.assertTrue(preview.rect().contains(canvas))
        preview.deleteLater()

    def test_gradient_end_color_preserves_transparency(self):
        project = Project.sample()
        text_id = next(
            str(field["id"])
            for field in project.comparison_items[0].display_fields()
            if field["type"] != "image"
        )
        project.field_styles[text_id] = {
            "background_color": "#ff0000",
            "gradient_color_2": "#000000ff",
            "fill_mode": "horizontal",
        }

        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        self.assertEqual(
            dialog.field_styles[text_id]["gradient_color_2"], "#000000ff"
        )
        self.assertTrue(dialog.band_gradient_button._allow_alpha)
        text_row = next(
            row
            for row in range(dialog.field_order_list.count())
            if dialog.field_order_list.item(row).data(Qt.ItemDataRole.UserRole)
            == text_id
        )
        dialog.field_order_list.setCurrentRow(text_row)
        direction_index = dialog.band_fill_combo.findData("diagonal_up_reverse")
        self.assertGreaterEqual(direction_index, 0)
        dialog.band_fill_combo.setCurrentIndex(direction_index)
        dialog.band_gradient_opacity_slider.setValue(35)
        saved_gradient = dialog.field_styles[text_id]["gradient_color_2"]
        self.assertEqual(dialog.field_styles[text_id]["fill_mode"], "diagonal_up_reverse")
        self.assertEqual(dialog.band_gradient_opacity_value.text(), "35%")
        self.assertAlmostEqual(QColor(saved_gradient).alpha(), round(255 * 0.35), delta=1)

        button = ColorButton("#000000ff", allow_alpha=True)
        self.assertEqual(button.color(), "#000000ff")
        self.assertEqual(button.text(), "TRANSPARENT")
        color_dialog = button._create_color_dialog()
        self.assertTrue(
            color_dialog.testOption(
                QColorDialog.ColorDialogOption.ShowAlphaChannel
            )
        )
        opacity_slider = color_dialog.findChild(QSlider, "ColorOpacitySlider")
        self.assertIsNotNone(opacity_slider)
        opacity_slider.setValue(42)
        self.assertAlmostEqual(
            color_dialog.currentColor().alpha(), round(255 * 0.42), delta=1
        )
        transparent_button = next(
            child
            for child in color_dialog.findChild(QDialogButtonBox).buttons()
            if child.text() == "Transparent"
        )
        transparent_button.click()
        self.assertEqual(color_dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(color_dialog.currentColor().alpha(), 0)
        color_dialog.deleteLater()
        button.deleteLater()
        dialog.apply_changes()
        dialog.deleteLater()

        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.field_styles[text_id]["gradient_color_2"], saved_gradient)
        self.assertEqual(
            restored.field_styles[text_id]["fill_mode"], "diagonal_up_reverse"
        )

    def test_shape_items_can_hold_text_and_persist(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        self.assertFalse(dialog.field_order_list.isHidden())
        self.assertFalse(dialog.box_preview.isAncestorOf(dialog.shape_palette_group))
        self.assertEqual(
            set(dialog.shape_tool_buttons),
            {
                "text",
                "rectangle",
                "rounded",
                "circle",
                "ellipse",
                "pill",
                "triangle",
                "diamond",
                "hexagon",
                "star",
            },
        )
        source_id = next(
            str(field["id"])
            for field in dialog._image_item.display_fields()
            if field["type"] != "image"
        )

        shape_id = dialog._add_content_item(source_id, "circle")
        fields = dialog._image_item.display_fields()
        shape_field = next(field for field in fields if field["id"] == shape_id)
        shape_field["value"] = "New badge"
        dialog._image_item.set_fields(fields)

        self.assertEqual(shape_field["type"], "shape")
        self.assertEqual(dialog.field_styles[shape_id]["shape"], "circle")
        self.assertTrue(dialog.field_order_list.currentItem().text().startswith("SHAPE"))
        dialog._preview_field_selected(shape_id)
        self.assertFalse(dialog.content_group.isHidden())
        self.assertFalse(dialog.field_label_edit.isHidden())
        self.assertFalse(dialog.field_value_edit.isHidden())
        dialog.field_value_edit.setText("Edited badge")
        dialog._selected_field_content_changed()
        fields = dialog._image_item.display_fields()
        shape_field = next(field for field in fields if field["id"] == shape_id)
        self.assertEqual(shape_field["value"], "Edited badge")
        for removed_control in (
            "shape_combo",
            "band_container_button",
            "band_border_button",
            "band_border_width_spin",
            "band_height_spin",
            "band_inset_spin",
            "band_corner_radius_spin",
        ):
            self.assertFalse(hasattr(dialog, removed_control))

        dialog.apply_changes()
        restored = Project.from_dict(project.to_dict())
        restored_shape = next(
            field
            for field in restored.comparison_items[0].display_fields()
            if field["id"] == shape_id
        )
        self.assertEqual(restored_shape["type"], "shape")
        self.assertEqual(restored_shape["value"], "Edited badge")
        self.assertEqual(restored.field_styles[shape_id]["shape"], "circle")
        dialog.deleteLater()

    def test_can_add_image_after_preview_image_deleted(self):
        project = Project.sample()
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        image_id = next(
            str(field.get("id", ""))
            for field in dialog._image_item.display_fields()
            if field.get("type") == "image"
        )
        dialog._remove_selected_content(image_id)
        self.assertFalse(
            any(field.get("type") == "image" for field in dialog._image_item.display_fields())
        )

        new_id = dialog._add_content_item(dialog._selected_field_id(), "image")
        fields = dialog._image_item.display_fields()
        self.assertEqual(fields[0].get("id"), new_id)
        self.assertEqual(fields[0].get("type"), "image")
        self.assertEqual(dialog.field_order_list.item(0).data(Qt.ItemDataRole.UserRole), new_id)
        dialog.deleteLater()

    def test_shape_gradient_and_free_geometry_survive_and_render(self):
        item = ComparisonItem(name="Gradient")
        item.set_fields(
            [
                {
                    "id": "title",
                    "type": "shape",
                    "label": "Title shape",
                    "value": "",
                    "role": "",
                }
            ]
        )
        project = Project(comparison_items=[item])
        project.field_styles = {
            "title": {
                "background_color": "#ff0000",
                "gradient_color_2": "#0000ff",
                "fill_mode": "horizontal",
                "text_color": "#ffffff",
                "shape": "ellipse",
                "overlay_x": "100",
                "overlay_y": "200",
                "overlay_width": "800",
                "overlay_height": "600",
            }
        }
        project.apply_fixed_item_timing()
        restored = Project.from_dict(project.to_dict())
        style = restored.field_styles["title"]
        self.assertEqual(style["shape"], "ellipse")
        self.assertEqual(style["fill_mode"], "horizontal")
        self.assertEqual(style["overlay_x"], "100")

        preview = PreviewWidget()
        preview.set_project(restored)
        frame = preview.render_frame(restored.item_fixed_duration)
        left = frame.pixelColor(130, 540)
        right = frame.pixelColor(510, 540)
        outside = frame.pixelColor(70, 230)
        self.assertGreater(left.red(), left.blue())
        self.assertGreater(right.blue(), right.red())
        self.assertEqual(outside, QColor(restored.canvas_background_color))
        preview.deleteLater()

    def test_custom_preset_replaces_default_fields_and_restores_shape_text(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = str(Path(directory) / "preferences.ini")
            item = ComparisonItem(name="Custom")
            item.set_fields(
                [
                    {
                        "id": "photo", "type": "image", "label": "Image",
                        "value": "", "role": "image",
                    },
                    {
                        "id": "year", "type": "shape", "label": "Rounded",
                        "value": "2003", "role": "",
                    },
                    {
                        "id": "caption", "type": "shape", "label": "Text",
                        "value": "First model", "role": "",
                    },
                ]
            )
            source = BoxCustomizationDialog(Project(comparison_items=[item]), item)
            source.preferences = QSettings(settings_path, QSettings.Format.IniFormat)
            source.field_styles["year"].update(
                {
                    "overlay_x": "100", "overlay_y": "800",
                    "overlay_width": "800", "overlay_height": "100",
                }
            )
            source.field_styles["caption"].update(
                {
                    "overlay_x": "100", "overlay_y": "600",
                    "overlay_width": "800", "overlay_height": "100",
                }
            )
            source.custom_presets = {"Custom": source._preset_from_current_controls()}
            self.assertTrue(source._save_custom_presets_to_preferences())
            source.deleteLater()

            project = Project.sample()
            project.comparison_items[0].image_transforms = {
                "field_image": {"scale_x": 1.5, "offset_x": 0.2}
            }
            dialog = BoxCustomizationDialog(project, project.comparison_items[0])
            dialog.preferences = QSettings(settings_path, QSettings.Format.IniFormat)
            dialog.custom_presets = dialog._load_custom_presets()
            dialog._populate_preset_combo("custom:Custom")
            dialog.field_order_list.setCurrentRow(1)
            for _ in range(2):
                dialog._apply_selected_preset()
                fields = dialog._image_item.display_fields()
                self.assertEqual(
                    [field["type"] for field in fields], ["image", "shape", "shape"]
                )
                self.assertEqual(
                    [field["value"] for field in fields[1:]], ["2003", "First model"]
                )
                self.assertEqual(dialog.field_styles[fields[1]["id"]]["overlay_y"], "800")
                self.assertEqual(dialog.field_styles[fields[2]["id"]]["overlay_y"], "600")
                self.assertEqual(dialog.field_order_list.count(), 3)
                field_ids = {field["id"] for field in fields}
                self.assertEqual(set(dialog.field_styles), field_ids)
                self.assertEqual(set(dialog.field_types), field_ids)
                self.assertEqual(set(dialog.field_roles), field_ids - {"field_image"})
                self.assertIn(dialog._selected_field_id(), field_ids)
            self.assertEqual(
                dialog._image_item.image_transforms["field_image"]["scale_x"], 1.5
            )
            dialog.apply_changes()
            restored = Project.from_dict(project.to_dict())
            for restored_item in restored.comparison_items:
                fields = restored_item.display_fields()
                self.assertEqual(
                    [field["type"] for field in fields], ["image", "shape", "shape"]
                )
                self.assertEqual(
                    [field["value"] for field in fields[1:]], ["2003", "First model"]
                )
            dialog.deleteLater()

    def test_custom_preset_keeps_each_items_values_for_matching_fields(self):
        project = Project.sample()
        original_names = [item.name for item in project.comparison_items]
        original_images = [item.image_path for item in project.comparison_items]
        dialog = BoxCustomizationDialog(project, project.comparison_items[0])
        preset = dialog._preset_from_current_controls()
        preset["objects"] = [
            obj for obj in preset["objects"] if obj["type"] in {"image", "name"}
        ]
        dialog.custom_presets = {"Image and name": preset}
        dialog._populate_preset_combo("custom:Image and name")
        dialog._apply_selected_preset()
        self.assertEqual(dialog.field_order_list.count(), 2)
        dialog.apply_changes()
        for index, item in enumerate(project.comparison_items):
            fields = item.display_fields()
            self.assertEqual([field["type"] for field in fields], ["image", "name"])
            self.assertEqual(
                [field["value"] for field in fields],
                [original_images[index], original_names[index]],
            )
        dialog.deleteLater()

    def test_custom_preset_is_flushed_and_restores_complete_object_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            settings_path = str(Path(directory) / "preferences.ini")
            project = Project.sample()
            dialog = BoxCustomizationDialog(project, project.comparison_items[0])
            dialog.preferences = QSettings(settings_path, QSettings.Format.IniFormat)
            dialog.columns_combo.setCurrentIndex(dialog.columns_combo.findData(4))
            fields = dialog._image_item.display_fields()
            image_id = next(str(field["id"]) for field in fields if field["type"] == "image")
            text_id = next(str(field["id"]) for field in fields if field["type"] != "image")
            dialog.field_styles[image_id].update(
                {
                    "shape": "ellipse",
                    "gradient_mode": "right",
                    "gradient_color": "#123456",
                    "overlay_x": "120",
                    "overlay_y": "80",
                    "overlay_width": "760",
                    "overlay_height": "640",
                }
            )
            dialog.field_styles[text_id].update(
                {
                    "shape": "pill",
                    "fill_mode": "horizontal",
                    "gradient_color_2": "#abcdef",
                    "parent_id": image_id,
                    "overlay_x": "100",
                    "overlay_y": "700",
                    "overlay_width": "800",
                    "overlay_height": "180",
                }
            )
            dialog._add_content_below(text_id)
            duplicate_id = next(iter(dialog._new_field_sources))
            dialog.field_styles[duplicate_id].update(
                {"shape": "diamond", "overlay_x": "250", "overlay_y": "300"}
            )
            dialog.custom_presets = {"My Layout": dialog._preset_from_current_controls()}
            dialog._save_custom_presets_to_preferences()
            dialog.deleteLater()

            reopened_project = Project.from_dict(project.to_dict())
            reopened = BoxCustomizationDialog(
                reopened_project, reopened_project.comparison_items[0]
            )
            reopened.preferences = QSettings(settings_path, QSettings.Format.IniFormat)
            reopened.custom_presets = reopened._load_custom_presets()
            self.assertIn("My Layout", reopened.custom_presets)
            reopened._populate_preset_combo("custom:My Layout")
            reopened._apply_selected_preset()
            self.assertEqual(reopened.columns_combo.currentData(), 4)

            image_style = reopened.field_styles[image_id]
            text_style = reopened.field_styles[text_id]
            self.assertEqual(image_style["shape"], "ellipse")
            self.assertEqual(image_style["gradient_mode"], "right")
            self.assertEqual(image_style["overlay_x"], "120")
            self.assertEqual(text_style["shape"], "rectangle")
            self.assertEqual(text_style["fill_mode"], "horizontal")
            self.assertEqual(text_style["gradient_color_2"], "#abcdef")
            self.assertEqual(text_style["parent_id"], image_id)
            duplicate = next(
                field
                for field in reopened._image_item.display_fields()
                if str(field.get("label", "")).endswith("copy")
            )
            restored_duplicate_id = str(duplicate["id"])
            self.assertEqual(
                reopened.field_styles[restored_duplicate_id]["shape"], "rectangle"
            )
            self.assertEqual(
                reopened._new_field_sources[restored_duplicate_id], text_id
            )
            reopened.deleteLater()


if __name__ == "__main__":
    unittest.main()
