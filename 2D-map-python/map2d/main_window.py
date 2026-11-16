from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QFile, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QWidget,
)

from .canvas import EditorCanvas
from .geometry import CABLE_TYPE_COLORS, cable_length_meters, round_coord
from .models import EditorData, create_initial_data, create_room, generate_default_room_name
from .persistence import DraftStore, ValidationError, export_project_json, load_project_file, save_project_file


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.draft_store = DraftStore()
        self.data: EditorData = self.draft_store.load() or create_initial_data()
        self.current_file: Path | None = None

        self._load_ui()
        self._bind_ui_widgets()
        self._configure_ui_defaults()

        self.canvas = EditorCanvas(self.data)
        self._mount_canvas()
        self._build_menu_actions()
        self.canvas.status_changed.connect(self._set_status)
        self.canvas.data_changed.connect(self._on_data_changed)
        self.canvas.selection_changed.connect(self._sync_forms_from_selection)

        self._connect_ui_signals()
        self._configure_input_direction()
        self._sync_forms_from_data()
        self._sync_forms_from_selection()

        self._set_status("Ready")

    def _load_ui(self) -> None:
        ui_path = Path(__file__).resolve().parent / "ui" / "main_window.ui"
        loader = QUiLoader()
        ui_file = QFile(str(ui_path))
        if not ui_file.open(QFile.OpenModeFlag.ReadOnly):
            raise RuntimeError(f"Cannot open UI file: {ui_path}")
        loaded = loader.load(ui_file)
        ui_file.close()
        if loaded is None:
            raise RuntimeError(f"Failed to load UI file: {ui_path}")
        if not isinstance(loaded, QMainWindow):
            raise RuntimeError(f"UI root is not QMainWindow: {ui_path}")

        self.setWindowTitle(loaded.windowTitle())
        self.resize(loaded.size())

        central = loaded.takeCentralWidget()
        if central is not None:
            self.setCentralWidget(central)
        menu_bar = loaded.menuBar()
        if menu_bar is not None:
            self.setMenuBar(menu_bar)
        status_bar = loaded.statusBar()
        if status_bar is not None:
            self.setStatusBar(status_bar)

        loaded.deleteLater()

    def _require_widget(self, widget_type: type[QWidget], object_name: str) -> QWidget:
        widget = self.findChild(widget_type, object_name)
        if widget is None:
            raise RuntimeError(f"Missing UI widget: {object_name}")
        return widget

    def _find_widget(self, widget_type: type[QWidget], object_name: str) -> QWidget | None:
        return self.findChild(widget_type, object_name)

    def _bind_ui_widgets(self) -> None:
        self.splitter_main = self._require_widget(QSplitter, "splitterMain")
        self.canvas_placeholder = self._require_widget(QWidget, "canvasPlaceholder")
        self.tabs = self._require_widget(QTabWidget, "tabs")

        # Room tab (active room))
        self.active_room_combo = self._require_widget(QComboBox, "activeRoomCombo")
        self.active_room_name = self._require_widget(QLineEdit, "activeRoomNameEdit")
        self.active_room_building = self._require_widget(QLineEdit, "activeRoomBuildingEdit")
        self.active_room_floor = self._require_widget(QLineEdit, "activeRoomFloorEdit")
        self.active_room_width = self._require_widget(QDoubleSpinBox, "activeRoomWidthSpin")
        self.active_room_height = self._require_widget(QDoubleSpinBox, "activeRoomHeightSpin")

        # Optional: these controls may be removed in customized .ui files.
        self.new_room_name = self._find_widget(QLineEdit, "newRoomNameEdit")
        self.new_room_building = self._find_widget(QLineEdit, "newRoomBuildingEdit")
        self.new_room_floor = self._find_widget(QLineEdit, "newRoomFloorEdit")
        self.new_room_width = self._find_widget(QDoubleSpinBox, "newRoomWidthSpin")
        self.new_room_height = self._find_widget(QDoubleSpinBox, "newRoomHeightSpin")

        self.create_room_button = self._require_widget(QPushButton, "createRoomButton")
        self.delete_active_room_button = self._require_widget(QPushButton, "deleteActiveRoomButton")
        self.mode_select_button = self._require_widget(QPushButton, "modeSelectButton")
        self.mode_edit_walls_button = self._require_widget(QPushButton, "modeEditWallsButton")
        self.mode_add_divider_wall_button = self._require_widget(QPushButton, "modeAddDividerWallButton")
        self.delete_wall_point_button = self._require_widget(QPushButton, "deleteWallPointButton")
        self.delete_divider_wall_button = self._require_widget(QPushButton, "deleteDividerWallButton")
        self.insert_wall_point = self._require_widget(QCheckBox, "insertWallPointCheck")
        self.snap_to_grid = self._require_widget(QCheckBox, "snapToGridCheck")
        self.room_grid_size = self._require_widget(QDoubleSpinBox, "roomGridSizeSpin")
        self.room_background_text = self._require_widget(QLineEdit, "roomBackgroundEdit")
        self.room_background_button = self._require_widget(QPushButton, "roomBackgroundButton")

        self.add_square_button = self._require_widget(QPushButton, "addSquareButton")
        self.add_rectangle_button = self._require_widget(QPushButton, "addRectangleButton")
        self.add_circle_button = self._require_widget(QPushButton, "addCircleButton")
        self.select_move_mode_button = self._require_widget(QPushButton, "selectMoveModeButton")
        self.delete_selected_object_button = self._require_widget(QPushButton, "deleteSelectedObjectButton")
        self.object_name = self._require_widget(QLineEdit, "objectNameEdit")
        self.object_label = self._require_widget(QLineEdit, "objectLabelEdit")
        self.object_comment = self._require_widget(QTextEdit, "objectCommentEdit")
        self.object_x = self._require_widget(QDoubleSpinBox, "objectXSpin")
        self.object_y = self._require_widget(QDoubleSpinBox, "objectYSpin")
        self.object_width = self._require_widget(QDoubleSpinBox, "objectWidthSpin")
        self.object_height = self._require_widget(QDoubleSpinBox, "objectHeightSpin")

        self.cable_type = self._require_widget(QComboBox, "cableTypeCombo")
        self.cable_label = self._require_widget(QLineEdit, "cableLabelEdit")
        self.cable_tag = self._require_widget(QLineEdit, "cableTagEdit")
        self.cable_comment = self._require_widget(QTextEdit, "cableCommentEdit")
        self.cable_diameter = self._require_widget(QDoubleSpinBox, "cableDiameterSpin")
        self.start_cable_placement_button = self._require_widget(QPushButton, "startCablePlacementButton")
        self.finish_cable_button = self._require_widget(QPushButton, "finishCableButton")
        self.cancel_cable_draft_button = self._require_widget(QPushButton, "cancelCableDraftButton")
        self.insert_bend_point_button = self._require_widget(QPushButton, "insertBendPointButton")
        self.delete_selected_cable_button = self._require_widget(QPushButton, "deleteSelectedCableButton")

        self.sel_cable_type = self._require_widget(QComboBox, "selCableTypeCombo")
        self.sel_cable_label = self._require_widget(QLineEdit, "selCableLabelEdit")
        self.sel_cable_tag = self._require_widget(QLineEdit, "selCableTagEdit")
        self.sel_cable_comment = self._require_widget(QTextEdit, "selCableCommentEdit")
        self.sel_cable_diameter = self._require_widget(QDoubleSpinBox, "selCableDiameterSpin")
        self.sel_length_mode = self._require_widget(QComboBox, "selLengthModeCombo")
        self.sel_fixed_length = self._require_widget(QDoubleSpinBox, "selFixedLengthSpin")
        self.sel_bend_radii = self._require_widget(QLineEdit, "selBendRadiiEdit")
        self.sel_total_length = self._require_widget(QLabel, "selTotalLengthLabel")
        self.sel_segment_lengths = self._require_widget(QLabel, "selSegmentLengthsLabel")

    def _configure_ui_defaults(self) -> None:
        self.active_room_width.setRange(1.0, 1000.0)
        self.active_room_height.setRange(1.0, 1000.0)
        if self.new_room_width is not None:
            self.new_room_width.setRange(1.0, 1000.0)
            self.new_room_width.setValue(6.0)
        if self.new_room_height is not None:
            self.new_room_height.setRange(1.0, 1000.0)
            self.new_room_height.setValue(5.0)

        self.room_grid_size.setRange(0.0, 50.0)
        self.room_grid_size.setSingleStep(0.1)
        self.snap_to_grid.setChecked(True)

        self.object_comment.setFixedHeight(64)
        self.object_x.setRange(0.0, 10000.0)
        self.object_y.setRange(0.0, 10000.0)
        self.object_width.setRange(0.1, 10000.0)
        self.object_height.setRange(0.1, 10000.0)

        self.cable_comment.setFixedHeight(64)
        self.cable_diameter.setRange(0.1, 500.0)
        self.cable_diameter.setValue(10.0)
        self.cable_type.clear()
        self.cable_type.addItems(["network", "power230", "power400", "fiber"])

        self.sel_cable_comment.setFixedHeight(64)
        self.sel_cable_diameter.setRange(0.1, 500.0)
        self.sel_length_mode.clear()
        self.sel_length_mode.addItems(["dynamic", "fixed"])
        self.sel_fixed_length.setRange(0.0, 100000.0)
        self.sel_cable_type.clear()
        self.sel_cable_type.addItems(["network", "power230", "power400", "fiber"])
        self.sel_segment_lengths.setWordWrap(True)
        self.sel_total_length.setText("-")
        self.sel_segment_lengths.setText("-")

        if self.new_room_name is not None:
            self.new_room_name.setText(generate_default_room_name(self.data.rooms))

    def _mount_canvas(self) -> None:
        placeholder_index = self.splitter_main.indexOf(self.canvas_placeholder)
        if placeholder_index >= 0:
            self.splitter_main.replaceWidget(placeholder_index, self.canvas)
            self.canvas_placeholder.deleteLater()
        else:
            self.splitter_main.insertWidget(0, self.canvas)
        self.splitter_main.setStretchFactor(0, 3)
        self.splitter_main.setStretchFactor(1, 1)
        self.splitter_main.setSizes([1100, 380])

    def _build_menu_actions(self) -> None:
        file_menu = self.findChild(QMenu, "menuFile")
        if file_menu is None:
            file_menu = self.menuBar().addMenu("&File")

        self.action_new_project = self.findChild(QAction, "actionNewProject") or QAction("New project", self)
        self.action_open_json = self.findChild(QAction, "actionOpenJson") or QAction("Open JSON...", self)
        self.action_save = self.findChild(QAction, "actionSave") or QAction("Save", self)
        self.action_save_as = self.findChild(QAction, "actionSaveAs") or QAction("Save As...", self)
        self.action_export_json = self.findChild(QAction, "actionExportJson") or QAction("Export JSON...", self)
        self.action_import_json = self.findChild(QAction, "actionImportJson") or QAction("Import JSON...", self)
        self.action_clear_autosave_draft = self.findChild(QAction, "actionClearAutosaveDraft") or QAction(
            "Clear autosave draft", self
        )

        for action in (
            self.action_new_project,
            self.action_open_json,
            self.action_save,
            self.action_save_as,
            self.action_export_json,
            self.action_import_json,
            self.action_clear_autosave_draft,
        ):
            if action not in file_menu.actions():
                file_menu.addAction(action)

    def _connect_ui_signals(self) -> None:
        self.action_new_project.triggered.connect(self._new_project)
        self.action_open_json.triggered.connect(self._open_project)
        self.action_save.triggered.connect(self._save_project)
        self.action_save_as.triggered.connect(self._save_project_as)
        self.action_export_json.triggered.connect(self._export_json)
        self.action_import_json.triggered.connect(self._open_project)
        self.action_clear_autosave_draft.triggered.connect(self._clear_draft)

        self.active_room_combo.currentIndexChanged.connect(self._on_active_room_change)
        self.active_room_name.editingFinished.connect(self._update_active_room_identity)
        self.active_room_building.editingFinished.connect(self._update_active_room_identity)
        self.active_room_floor.editingFinished.connect(self._update_active_room_identity)
        self.active_room_width.valueChanged.connect(self._update_active_room_dimensions)
        self.active_room_height.valueChanged.connect(self._update_active_room_dimensions)

        self.create_room_button.clicked.connect(self._create_room)
        self.delete_active_room_button.clicked.connect(self._delete_active_room)
        self.mode_select_button.clicked.connect(lambda: self.canvas.set_mode("select"))
        self.mode_edit_walls_button.clicked.connect(lambda: self.canvas.set_mode("edit-walls"))
        self.mode_add_divider_wall_button.clicked.connect(lambda: self.canvas.set_mode("add-divider-wall"))
        self.delete_wall_point_button.clicked.connect(self._delete_selected_wall_point)
        self.delete_divider_wall_button.clicked.connect(self._delete_selected_divider_wall)
        self.insert_wall_point.toggled.connect(self.canvas.set_insert_wall_point_mode)
        self.snap_to_grid.toggled.connect(self.canvas.set_snap_to_grid)
        self.room_grid_size.valueChanged.connect(self._update_room_properties)
        self.room_background_text.editingFinished.connect(self._update_room_properties)
        self.room_background_button.clicked.connect(self._pick_room_color)

        self.add_square_button.clicked.connect(lambda: self.canvas.set_mode("add-object-square"))
        self.add_rectangle_button.clicked.connect(lambda: self.canvas.set_mode("add-object-rectangle"))
        self.add_circle_button.clicked.connect(lambda: self.canvas.set_mode("add-object-circle"))
        self.select_move_mode_button.clicked.connect(lambda: self.canvas.set_mode("select"))
        self.delete_selected_object_button.clicked.connect(self._delete_selected_object)

        for widget in (self.object_name, self.object_label):
            widget.editingFinished.connect(self._update_selected_object)
        self.object_comment.textChanged.connect(self._update_selected_object)
        for spin in (self.object_x, self.object_y, self.object_width, self.object_height):
            spin.valueChanged.connect(self._update_selected_object)

        self.start_cable_placement_button.clicked.connect(self._start_cable_draft)
        self.finish_cable_button.clicked.connect(self.canvas.finish_cable_draft)
        self.cancel_cable_draft_button.clicked.connect(self.canvas.cancel_cable_draft)
        self.insert_bend_point_button.clicked.connect(self.canvas.insert_point_on_selected_cable_segment)
        self.delete_selected_cable_button.clicked.connect(self._delete_selected_cable)

        self.sel_cable_type.currentTextChanged.connect(self._update_selected_cable)
        self.sel_cable_label.editingFinished.connect(self._update_selected_cable)
        self.sel_cable_tag.editingFinished.connect(self._update_selected_cable)
        self.sel_cable_comment.textChanged.connect(self._update_selected_cable)
        self.sel_cable_diameter.valueChanged.connect(self._update_selected_cable)
        self.sel_length_mode.currentTextChanged.connect(self._update_selected_cable)
        self.sel_fixed_length.valueChanged.connect(self._update_selected_cable)
        self.sel_bend_radii.editingFinished.connect(self._update_selected_cable)

    def _set_status(self, message: str) -> None:
        if self.statusBar() is not None:
            self.statusBar().showMessage(message)

    def _configure_input_direction(self) -> None:
        line_edits = [
            self.active_room_name,
            self.active_room_building,
            self.active_room_floor,
            self.new_room_name,
            self.new_room_building,
            self.new_room_floor,
            self.room_background_text,
            self.object_name,
            self.object_label,
            self.cable_label,
            self.cable_tag,
            self.sel_cable_label,
            self.sel_cable_tag,
            self.sel_bend_radii,
        ]
        for widget in line_edits:
            if widget is None:
                continue
            widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            widget.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            widget.setCursorMoveStyle(Qt.CursorMoveStyle.LogicalMoveStyle)

        text_edits = (
            self.object_comment,
            self.cable_comment,
            self.sel_cable_comment,
        )
        for widget in text_edits:
            widget.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
            widget.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def _new_project(self) -> None:
        self.data = create_initial_data()
        self.canvas.data = self.data
        self.current_file = None
        self._sync_forms_from_data()
        self._sync_forms_from_selection()
        self.canvas.update()
        self._on_data_changed()
        self._set_status("New project created.")

    def _open_project(self) -> None:
        path_text, _ = QFileDialog.getOpenFileName(
            self,
            "Open 2D map JSON",
            "",
            "JSON files (*.json);;All files (*)",
        )
        if not path_text:
            return
        path = Path(path_text)
        try:
            self.data = load_project_file(path)
        except (ValidationError, OSError) as error:
            QMessageBox.critical(self, "Open failed", str(error))
            return

        self.canvas.data = self.data
        self.current_file = path
        self._sync_forms_from_data()
        self._sync_forms_from_selection()
        self.canvas.update()
        self._on_data_changed()
        self._set_status(f"Loaded {path.name}")

    def _save_project(self) -> None:
        if self.current_file is None:
            self._save_project_as()
            return
        try:
            save_project_file(self.current_file, self.data)
            self._set_status(f"Saved {self.current_file.name}")
        except OSError as error:
            QMessageBox.critical(self, "Save failed", str(error))

    def _save_project_as(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Save 2D map JSON",
            "2d-map-project.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path_text:
            return
        self.current_file = Path(path_text)
        self._save_project()

    def _export_json(self) -> None:
        path_text, _ = QFileDialog.getSaveFileName(
            self,
            "Export JSON",
            "2d-map-export.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path_text:
            return
        path = Path(path_text)
        try:
            path.write_text(export_project_json(self.data), encoding="utf-8")
            self._set_status(f"Exported {path.name}")
        except OSError as error:
            QMessageBox.critical(self, "Export failed", str(error))

    def _clear_draft(self) -> None:
        self.draft_store.clear()
        self._set_status("Draft cleared.")

    def _create_room(self) -> None:
        room_name = generate_default_room_name(self.data.rooms)
        if self.new_room_name is not None:
            room_name = self.new_room_name.text().strip() or room_name

        width_meters = self.new_room_width.value() if self.new_room_width is not None else 6.0
        height_meters = self.new_room_height.value() if self.new_room_height is not None else 5.0
        building = self.new_room_building.text().strip() if self.new_room_building is not None else ""
        floor = self.new_room_floor.text().strip() if self.new_room_floor is not None else ""
        room = create_room(
            name=room_name,
            width_meters=width_meters,
            height_meters=height_meters,
            building=building,
            floor=floor,
        )
        self.data.rooms.append(room)
        self.data.active_room_id = room.id
        if self.new_room_name is not None:
            self.new_room_name.setText(generate_default_room_name(self.data.rooms))
        if self.new_room_building is not None:
            self.new_room_building.clear()
        if self.new_room_floor is not None:
            self.new_room_floor.clear()
        self._sync_forms_from_data()
        self._on_data_changed()
        self.canvas.update()
        self._set_status(f"Room created: {room.name}")

    def _on_active_room_change(self, index: int) -> None:
        if index < 0 or index >= len(self.data.rooms):
            return
        self.data.active_room_id = self.data.rooms[index].id
        self.canvas.clear_selection()
        self._sync_forms_from_data()
        self.canvas.update()
        self._on_data_changed()

    def _update_room_properties(self) -> None:
        room = self.canvas.active_room
        if room is None:
            return
        room.grid_size_meters = round_coord(self.room_grid_size.value())
        color = self.room_background_text.text().strip()
        if color:
            room.background = color
        self.canvas.update()
        self._on_data_changed()

    def _pick_room_color(self) -> None:
        room = self.canvas.active_room
        if room is None:
            return
        color = QColorDialog.getColor(QColor(room.background), self, "Room background color")
        if not color.isValid():
            return
        room.background = color.name()
        self.room_background_text.setText(room.background)
        self.canvas.update()
        self._on_data_changed()

    def _update_active_room_identity(self) -> None:
        room = self.canvas.active_room
        if room is None:
            return
        updated_name = self.active_room_name.text().strip() or "Room"
        updated_building = self.active_room_building.text().strip()
        updated_floor = self.active_room_floor.text().strip()
        if (
            room.name == updated_name
            and room.building == updated_building
            and room.floor == updated_floor
        ):
            return
        room.name = updated_name
        room.building = updated_building
        room.floor = updated_floor
        self._on_data_changed()
        self._set_status(f"Updated room metadata for: {room.name}")

    def _update_active_room_dimensions(self) -> None:
        room = self.canvas.active_room
        if room is None:
            return
        new_width = round_coord(self.active_room_width.value())
        new_height = round_coord(self.active_room_height.value())
        old_width = room.width_meters
        old_height = room.height_meters
        if abs(new_width - old_width) < 1e-9 and abs(new_height - old_height) < 1e-9:
            return

        scale_x = 1.0 if old_width <= 0 else new_width / old_width
        scale_y = 1.0 if old_height <= 0 else new_height / old_height
        room.width_meters = new_width
        room.height_meters = new_height

        for point in room.wall_points:
            point.x = round_coord(point.x * scale_x)
            point.y = round_coord(point.y * scale_y)

        for wall in room.divider_walls:
            wall.from_point.x = round_coord(wall.from_point.x * scale_x)
            wall.from_point.y = round_coord(wall.from_point.y * scale_y)
            wall.to_point.x = round_coord(wall.to_point.x * scale_x)
            wall.to_point.y = round_coord(wall.to_point.y * scale_y)

        for obj in self.data.objects:
            if obj.room_id != room.id:
                continue
            obj.x = round_coord(obj.x * scale_x)
            obj.y = round_coord(obj.y * scale_y)
            obj.width = max(0.1, round_coord(obj.width * scale_x))
            obj.height = max(0.1, round_coord(obj.height * scale_y))
            obj.x = min(obj.x, max(0.0, round_coord(new_width - obj.width)))
            obj.y = min(obj.y, max(0.0, round_coord(new_height - obj.height)))

        for cable in self.data.cables:
            for point in cable.points:
                if point.room_id != room.id:
                    continue
                point.x = min(new_width, max(0.0, round_coord(point.x * scale_x)))
                point.y = min(new_height, max(0.0, round_coord(point.y * scale_y)))

        self.canvas.update()
        self._on_data_changed()
        self._set_status(f"Resized room to {new_width:.2f}m x {new_height:.2f}m")

    def _start_cable_draft(self) -> None:
        self.canvas.set_cable_draft_meta(
            self.cable_type.currentText(),  # type: ignore[arg-type]
            self.cable_label.text().strip(),
            self.cable_tag.text().strip(),
            self.cable_comment.toPlainText().strip(),
            self.cable_diameter.value(),
        )
        self.canvas.set_mode("add-cable")
        self._set_status("Cable placement started. Left-click to add points, right-click to finish.")

    def _sync_forms_from_data(self) -> None:
        current_room_id = self.data.active_room_id
        if self.data.rooms and current_room_id not in {room.id for room in self.data.rooms}:
            self.data.active_room_id = self.data.rooms[0].id
            current_room_id = self.data.active_room_id

        self.active_room_combo.blockSignals(True)
        self.active_room_combo.clear()
        for room in self.data.rooms:
            self.active_room_combo.addItem(room.name, room.id)
        selected_index = 0
        for index, room in enumerate(self.data.rooms):
            if room.id == current_room_id:
                selected_index = index
                break
        self.active_room_combo.setCurrentIndex(selected_index if self.data.rooms else -1)
        self.active_room_combo.blockSignals(False)

        room = self.canvas.active_room
        if room:
            self.active_room_name.blockSignals(True)
            self.active_room_building.blockSignals(True)
            self.active_room_floor.blockSignals(True)
            self.active_room_width.blockSignals(True)
            self.active_room_height.blockSignals(True)
            self.room_grid_size.blockSignals(True)
            self.active_room_name.setText(room.name)
            self.active_room_building.setText(room.building)
            self.active_room_floor.setText(room.floor)
            self.active_room_width.setValue(room.width_meters)
            self.active_room_height.setValue(room.height_meters)
            self.room_grid_size.setValue(room.grid_size_meters)
            self.room_grid_size.blockSignals(False)
            self.active_room_name.blockSignals(False)
            self.active_room_building.blockSignals(False)
            self.active_room_floor.blockSignals(False)
            self.active_room_width.blockSignals(False)
            self.active_room_height.blockSignals(False)
            self.room_background_text.setText(room.background)

        if self.new_room_name is not None and self.data.rooms and not self.new_room_name.text().strip():
            self.new_room_name.setText(generate_default_room_name(self.data.rooms))

    def _sync_forms_from_selection(self) -> None:
        selected_object = next(
            (obj for obj in self.data.objects if obj.id == self.canvas.selected_object_id),
            None,
        )
        self._set_object_form_enabled(selected_object is not None)
        if selected_object:
            self.object_name.blockSignals(True)
            self.object_label.blockSignals(True)
            self.object_comment.blockSignals(True)
            self.object_x.blockSignals(True)
            self.object_y.blockSignals(True)
            self.object_width.blockSignals(True)
            self.object_height.blockSignals(True)

            self.object_name.setText(selected_object.name)
            self.object_label.setText(selected_object.label)
            self.object_comment.setText(selected_object.comment)
            self.object_x.setValue(selected_object.x)
            self.object_y.setValue(selected_object.y)
            self.object_width.setValue(selected_object.width)
            self.object_height.setValue(selected_object.height)

            self.object_name.blockSignals(False)
            self.object_label.blockSignals(False)
            self.object_comment.blockSignals(False)
            self.object_x.blockSignals(False)
            self.object_y.blockSignals(False)
            self.object_width.blockSignals(False)
            self.object_height.blockSignals(False)

        selected_cable = next(
            (cable for cable in self.data.cables if cable.id == self.canvas.selected_cable_id),
            None,
        )
        self._set_cable_form_enabled(selected_cable is not None)
        if selected_cable:
            self.sel_cable_type.blockSignals(True)
            self.sel_cable_label.blockSignals(True)
            self.sel_cable_tag.blockSignals(True)
            self.sel_cable_comment.blockSignals(True)
            self.sel_cable_diameter.blockSignals(True)
            self.sel_length_mode.blockSignals(True)
            self.sel_fixed_length.blockSignals(True)
            self.sel_bend_radii.blockSignals(True)

            self.sel_cable_type.setCurrentText(selected_cable.type)
            self.sel_cable_label.setText(selected_cable.label)
            self.sel_cable_tag.setText(selected_cable.tag)
            self.sel_cable_comment.setText(selected_cable.comment)
            self.sel_cable_diameter.setValue(selected_cable.diameter_mm)
            self.sel_length_mode.setCurrentText(selected_cable.length_mode)
            self.sel_fixed_length.setValue(selected_cable.fixed_length_meters or 0.0)
            self.sel_bend_radii.setText(", ".join(f"{round_coord(value):.2f}" for value in selected_cable.bend_radius_meters))

            self.sel_cable_type.blockSignals(False)
            self.sel_cable_label.blockSignals(False)
            self.sel_cable_tag.blockSignals(False)
            self.sel_cable_comment.blockSignals(False)
            self.sel_cable_diameter.blockSignals(False)
            self.sel_length_mode.blockSignals(False)
            self.sel_fixed_length.blockSignals(False)
            self.sel_bend_radii.blockSignals(False)

            length = cable_length_meters(selected_cable)
            self.sel_total_length.setText(f"{round_coord(length):.2f}")
            segments: list[str] = []
            for idx in range(1, len(selected_cable.points)):
                prev = selected_cable.points[idx - 1]
                cur = selected_cable.points[idx]
                if prev.room_id == cur.room_id:
                    segment = ((prev.x - cur.x) ** 2 + (prev.y - cur.y) ** 2) ** 0.5
                else:
                    segment = 0.0
                segments.append(f"S{idx}: {round_coord(segment):.2f}")
            self.sel_segment_lengths.setText(", ".join(segments) if segments else "-")
            self.sel_fixed_length.setEnabled(selected_cable.length_mode == "fixed")
        else:
            self.sel_total_length.setText("-")
            self.sel_segment_lengths.setText("-")
            self.sel_bend_radii.setText("")

    def _set_object_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self.object_name,
            self.object_label,
            self.object_comment,
            self.object_x,
            self.object_y,
            self.object_width,
            self.object_height,
        ):
            widget.setEnabled(enabled)

    def _set_cable_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self.sel_cable_type,
            self.sel_cable_label,
            self.sel_cable_tag,
            self.sel_cable_comment,
            self.sel_cable_diameter,
            self.sel_length_mode,
            self.sel_fixed_length,
            self.sel_bend_radii,
        ):
            widget.setEnabled(enabled)

    def _update_selected_object(self) -> None:
        selected_object = next(
            (obj for obj in self.data.objects if obj.id == self.canvas.selected_object_id),
            None,
        )
        if selected_object is None:
            return
        selected_object.name = self.object_name.text().strip()
        selected_object.label = self.object_label.text().strip()
        selected_object.comment = self.object_comment.toPlainText().strip()
        selected_object.x = round_coord(self.object_x.value())
        selected_object.y = round_coord(self.object_y.value())
        selected_object.width = round_coord(self.object_width.value())
        selected_object.height = round_coord(self.object_height.value())
        self.canvas.update()
        self._on_data_changed()

    def _update_selected_cable(self) -> None:
        selected_cable = next(
            (cable for cable in self.data.cables if cable.id == self.canvas.selected_cable_id),
            None,
        )
        if selected_cable is None:
            return
        selected_cable.type = self.sel_cable_type.currentText()  # type: ignore[assignment]
        selected_cable.color = CABLE_TYPE_COLORS[selected_cable.type]
        selected_cable.label = self.sel_cable_label.text().strip()
        selected_cable.tag = self.sel_cable_tag.text().strip()
        selected_cable.comment = self.sel_cable_comment.toPlainText().strip()
        selected_cable.diameter_mm = round_coord(self.sel_cable_diameter.value())
        selected_cable.length_mode = self.sel_length_mode.currentText()  # type: ignore[assignment]
        if selected_cable.length_mode == "fixed":
            selected_cable.fixed_length_meters = round_coord(self.sel_fixed_length.value())
        else:
            selected_cable.fixed_length_meters = None
        bend_csv = self.sel_bend_radii.text().strip()
        if bend_csv:
            parsed: list[float] = []
            for item in bend_csv.split(","):
                text = item.strip()
                if not text:
                    continue
                try:
                    parsed.append(round_coord(float(text)))
                except ValueError:
                    self._set_status("Invalid bend radius list. Use comma-separated numbers.")
                    return
            selected_cable.bend_radius_meters = parsed
        else:
            selected_cable.bend_radius_meters = []
        self.canvas.update()
        self._on_data_changed()
        self._sync_forms_from_selection()

    def _delete_selected_wall_point(self) -> None:
        room = self.canvas.active_room
        point_index = self.canvas.selected_wall_point_index
        if room is None or point_index is None:
            self._set_status("No wall point selected.")
            return
        if len(room.wall_points) <= 3:
            self._set_status("A room needs at least 3 wall points.")
            return
        if point_index < 0 or point_index >= len(room.wall_points):
            return
        del room.wall_points[point_index]
        self.canvas.selected_wall_point_index = None
        self.canvas.update()
        self._on_data_changed()
        self._set_status("Wall point deleted.")

    def _delete_active_room(self) -> None:
        room = self.canvas.active_room
        if room is None:
            self._set_status("No active room to delete.")
            return
        if len(self.data.rooms) <= 1:
            self._set_status("At least one room must remain in the project.")
            return
        reply = QMessageBox.question(
            self,
            "Delete room",
            f"Delete room '{room.name}' and all associated room objects/cables?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.data.rooms = [item for item in self.data.rooms if item.id != room.id]
        self.data.objects = [obj for obj in self.data.objects if obj.room_id != room.id]
        self.data.cables = [
            cable for cable in self.data.cables if not any(point.room_id == room.id for point in cable.points)
        ]
        self.data.active_room_id = self.data.rooms[0].id if self.data.rooms else None
        self.canvas.clear_selection()
        self._on_data_changed()
        self._set_status(f"Deleted room: {room.name}")

    def _delete_selected_divider_wall(self) -> None:
        room = self.canvas.active_room
        index = self.canvas.selected_divider_wall_index
        if room is None or index is None:
            self._set_status("No divider wall selected.")
            return
        if 0 <= index < len(room.divider_walls):
            del room.divider_walls[index]
        self.canvas.selected_divider_wall_index = None
        self.canvas.update()
        self._on_data_changed()
        self._set_status("Divider wall deleted.")

    def _delete_selected_object(self) -> None:
        object_id = self.canvas.selected_object_id
        if object_id is None:
            self._set_status("No object selected.")
            return
        self.data.objects = [obj for obj in self.data.objects if obj.id != object_id]
        self.canvas.selected_object_id = None
        self.canvas.update()
        self._on_data_changed()
        self._set_status("Object deleted.")

    def _delete_selected_cable(self) -> None:
        cable_id = self.canvas.selected_cable_id
        if cable_id is None:
            self._set_status("No cable selected.")
            return
        self.data.cables = [cable for cable in self.data.cables if cable.id != cable_id]
        self.canvas.selected_cable_id = None
        self.canvas.selected_cable_point_index = None
        self.canvas.selected_cable_segment_index = None
        self.canvas.update()
        self._on_data_changed()
        self._set_status("Cable deleted.")

    def _on_data_changed(self) -> None:
        self._sync_forms_from_data()
        self._sync_forms_from_selection()
        self.draft_store.save(self.data)


def run() -> None:
    # Avoid hard failures from some Linux desktop theme integrations when
    # GNOME settings schemas are incomplete/inconsistent.
    QApplication.setDesktopSettingsAware(False)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
