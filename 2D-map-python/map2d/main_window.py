from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .canvas import EditorCanvas
from .geometry import CABLE_TYPE_COLORS, cable_length_meters, round_coord
from .models import EditorData, create_initial_data, create_room, generate_default_room_name
from .persistence import DraftStore, ValidationError, export_project_json, load_project_file, save_project_file


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("2D-map Python (PySide6)")
        self.resize(1500, 920)

        self.draft_store = DraftStore()
        self.data: EditorData = self.draft_store.load() or create_initial_data()
        self.current_file: Path | None = None

        self.canvas = EditorCanvas(self.data)
        self.canvas.status_changed.connect(self._set_status)
        self.canvas.data_changed.connect(self._on_data_changed)
        self.canvas.selection_changed.connect(self._sync_forms_from_selection)

        self._build_menu()
        self._build_ui()
        self._configure_input_direction()
        self._sync_forms_from_data()
        self._sync_forms_from_selection()

        self._set_status("Ready")

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("&File")

        action_new = QAction("New project", self)
        action_new.triggered.connect(self._new_project)
        menu.addAction(action_new)

        action_open = QAction("Open JSON...", self)
        action_open.triggered.connect(self._open_project)
        menu.addAction(action_open)

        action_save = QAction("Save", self)
        action_save.triggered.connect(self._save_project)
        menu.addAction(action_save)

        action_save_as = QAction("Save As...", self)
        action_save_as.triggered.connect(self._save_project_as)
        menu.addAction(action_save_as)

        action_export = QAction("Export JSON...", self)
        action_export.triggered.connect(self._export_json)
        menu.addAction(action_export)

        action_import = QAction("Import JSON...", self)
        action_import.triggered.connect(self._open_project)
        menu.addAction(action_import)

        menu.addSeparator()
        action_clear_draft = QAction("Clear autosave draft", self)
        action_clear_draft.triggered.connect(self._clear_draft)
        menu.addAction(action_clear_draft)

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(6, 6, 6, 6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.canvas)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(6, 6, 6, 6)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_room_tab(), "Room")
        self.tabs.addTab(self._build_objects_tab(), "Objects")
        self.tabs.addTab(self._build_cables_tab(), "Cables")
        side_layout.addWidget(self.tabs)

        splitter.addWidget(side_panel)
        splitter.setSizes([1100, 380])

        root_layout.addWidget(splitter)
        self.setCentralWidget(root)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

    def _build_room_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        room_selector_layout = QHBoxLayout()
        room_selector_layout.addWidget(QLabel("Active room:"))
        self.active_room_combo = QComboBox()
        self.active_room_combo.currentIndexChanged.connect(self._on_active_room_change)
        room_selector_layout.addWidget(self.active_room_combo)
        layout.addLayout(room_selector_layout)

        active_form = QFormLayout()
        self.active_room_name = QLineEdit()
        self.active_room_name.editingFinished.connect(self._update_active_room_identity)
        self.active_room_building = QLineEdit()
        self.active_room_building.editingFinished.connect(self._update_active_room_identity)
        self.active_room_floor = QLineEdit()
        self.active_room_floor.editingFinished.connect(self._update_active_room_identity)
        self.active_room_width = QDoubleSpinBox()
        self.active_room_width.setRange(1.0, 1000.0)
        self.active_room_width.valueChanged.connect(self._update_active_room_dimensions)
        self.active_room_height = QDoubleSpinBox()
        self.active_room_height.setRange(1.0, 1000.0)
        self.active_room_height.valueChanged.connect(self._update_active_room_dimensions)
        active_form.addRow("Building", self.active_room_building)
        active_form.addRow("Floor", self.active_room_floor)
        active_form.addRow("Room name", self.active_room_name)
        active_form.addRow("Room width (m)", self.active_room_width)
        active_form.addRow("Room height (m)", self.active_room_height)
        layout.addLayout(active_form)

        create_form = QFormLayout()
        self.new_room_name = QLineEdit(generate_default_room_name(self.data.rooms))
        self.new_room_building = QLineEdit()
        self.new_room_floor = QLineEdit()
        self.new_room_width = QDoubleSpinBox()
        self.new_room_width.setRange(1.0, 1000.0)
        self.new_room_width.setValue(6.0)
        self.new_room_height = QDoubleSpinBox()
        self.new_room_height.setRange(1.0, 1000.0)
        self.new_room_height.setValue(5.0)
        create_form.addRow("Building", self.new_room_building)
        create_form.addRow("Floor", self.new_room_floor)
        create_form.addRow("Name", self.new_room_name)
        create_form.addRow("Width (m)", self.new_room_width)
        create_form.addRow("Height (m)", self.new_room_height)
        layout.addLayout(create_form)

        add_room_btn = QPushButton("Create room")
        add_room_btn.clicked.connect(self._create_room)
        layout.addWidget(add_room_btn)
        delete_room_btn = QPushButton("Delete active room")
        delete_room_btn.clicked.connect(self._delete_active_room)
        layout.addWidget(delete_room_btn)

        mode_layout = QHBoxLayout()
        mode_select = QPushButton("Select")
        mode_select.clicked.connect(lambda: self.canvas.set_mode("select"))
        mode_walls = QPushButton("Edit walls")
        mode_walls.clicked.connect(lambda: self.canvas.set_mode("edit-walls"))
        mode_divider = QPushButton("Add divider wall")
        mode_divider.clicked.connect(lambda: self.canvas.set_mode("add-divider-wall"))
        mode_layout.addWidget(mode_select)
        mode_layout.addWidget(mode_walls)
        mode_layout.addWidget(mode_divider)
        layout.addLayout(mode_layout)
        delete_wall_point_btn = QPushButton("Delete selected wall point")
        delete_wall_point_btn.clicked.connect(self._delete_selected_wall_point)
        layout.addWidget(delete_wall_point_btn)
        delete_divider_btn = QPushButton("Delete selected divider wall")
        delete_divider_btn.clicked.connect(self._delete_selected_divider_wall)
        layout.addWidget(delete_divider_btn)

        self.insert_wall_point = QCheckBox("Insert wall points when clicking edges")
        self.insert_wall_point.toggled.connect(self.canvas.set_insert_wall_point_mode)
        layout.addWidget(self.insert_wall_point)

        self.snap_to_grid = QCheckBox("Snap to grid")
        self.snap_to_grid.setChecked(True)
        self.snap_to_grid.toggled.connect(self.canvas.set_snap_to_grid)
        layout.addWidget(self.snap_to_grid)

        room_props_form = QFormLayout()
        self.room_grid_size = QDoubleSpinBox()
        self.room_grid_size.setRange(0.0, 50.0)
        self.room_grid_size.setSingleStep(0.1)
        self.room_grid_size.valueChanged.connect(self._update_room_properties)

        self.room_background_text = QLineEdit()
        self.room_background_text.editingFinished.connect(self._update_room_properties)
        self.room_background_button = QPushButton("Pick color")
        self.room_background_button.clicked.connect(self._pick_room_color)

        room_props_form.addRow("Grid size (m)", self.room_grid_size)
        room_props_form.addRow("Background", self.room_background_text)
        room_props_form.addRow("", self.room_background_button)
        layout.addLayout(room_props_form)

        layout.addStretch(1)
        return tab

    def _build_objects_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        object_buttons = QHBoxLayout()
        for shape in ("square", "rectangle", "circle"):
            button = QPushButton(f"Add {shape}")
            button.clicked.connect(lambda _checked=False, s=shape: self.canvas.set_mode(f"add-object-{s}"))
            object_buttons.addWidget(button)
        layout.addLayout(object_buttons)

        select_btn = QPushButton("Select / move mode")
        select_btn.clicked.connect(lambda: self.canvas.set_mode("select"))
        layout.addWidget(select_btn)
        delete_btn = QPushButton("Delete selected object")
        delete_btn.clicked.connect(self._delete_selected_object)
        layout.addWidget(delete_btn)

        form = QFormLayout()
        self.object_name = QLineEdit()
        self.object_label = QLineEdit()
        self.object_comment = QTextEdit()
        self.object_comment.setFixedHeight(64)
        self.object_x = QDoubleSpinBox()
        self.object_x.setRange(0.0, 10000.0)
        self.object_y = QDoubleSpinBox()
        self.object_y.setRange(0.0, 10000.0)
        self.object_width = QDoubleSpinBox()
        self.object_width.setRange(0.1, 10000.0)
        self.object_height = QDoubleSpinBox()
        self.object_height.setRange(0.1, 10000.0)

        for widget in (self.object_name, self.object_label):
            widget.editingFinished.connect(self._update_selected_object)
        self.object_comment.textChanged.connect(self._update_selected_object)
        for spin in (self.object_x, self.object_y, self.object_width, self.object_height):
            spin.valueChanged.connect(self._update_selected_object)

        form.addRow("Name", self.object_name)
        form.addRow("Label", self.object_label)
        form.addRow("Comment", self.object_comment)
        form.addRow("X", self.object_x)
        form.addRow("Y", self.object_y)
        form.addRow("Width", self.object_width)
        form.addRow("Height", self.object_height)
        layout.addLayout(form)

        layout.addStretch(1)
        return tab

    def _build_cables_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        form = QFormLayout()
        self.cable_type = QComboBox()
        self.cable_type.addItems(["network", "power230", "power400", "fiber"])
        self.cable_label = QLineEdit()
        self.cable_tag = QLineEdit()
        self.cable_comment = QTextEdit()
        self.cable_comment.setFixedHeight(64)
        self.cable_diameter = QDoubleSpinBox()
        self.cable_diameter.setRange(0.1, 500.0)
        self.cable_diameter.setValue(10.0)

        form.addRow("New cable type", self.cable_type)
        form.addRow("Label", self.cable_label)
        form.addRow("Tag", self.cable_tag)
        form.addRow("Comment", self.cable_comment)
        form.addRow("Diameter (mm)", self.cable_diameter)
        layout.addLayout(form)

        draft_row = QHBoxLayout()
        start_btn = QPushButton("Start cable placement")
        start_btn.clicked.connect(self._start_cable_draft)
        finish_btn = QPushButton("Finish cable")
        finish_btn.clicked.connect(self.canvas.finish_cable_draft)
        cancel_btn = QPushButton("Cancel cable draft")
        cancel_btn.clicked.connect(self.canvas.cancel_cable_draft)
        draft_row.addWidget(start_btn)
        draft_row.addWidget(finish_btn)
        draft_row.addWidget(cancel_btn)
        layout.addLayout(draft_row)

        insert_bend_btn = QPushButton("Insert bend point on selected segment")
        insert_bend_btn.clicked.connect(self.canvas.insert_point_on_selected_cable_segment)
        layout.addWidget(insert_bend_btn)
        delete_cable_btn = QPushButton("Delete selected cable")
        delete_cable_btn.clicked.connect(self._delete_selected_cable)
        layout.addWidget(delete_cable_btn)

        selected_form = QFormLayout()
        self.sel_cable_type = QComboBox()
        self.sel_cable_type.addItems(["network", "power230", "power400", "fiber"])
        self.sel_cable_type.currentTextChanged.connect(self._update_selected_cable)
        self.sel_cable_label = QLineEdit()
        self.sel_cable_label.editingFinished.connect(self._update_selected_cable)
        self.sel_cable_tag = QLineEdit()
        self.sel_cable_tag.editingFinished.connect(self._update_selected_cable)
        self.sel_cable_comment = QTextEdit()
        self.sel_cable_comment.setFixedHeight(64)
        self.sel_cable_comment.textChanged.connect(self._update_selected_cable)
        self.sel_cable_diameter = QDoubleSpinBox()
        self.sel_cable_diameter.setRange(0.1, 500.0)
        self.sel_cable_diameter.valueChanged.connect(self._update_selected_cable)
        self.sel_length_mode = QComboBox()
        self.sel_length_mode.addItems(["dynamic", "fixed"])
        self.sel_length_mode.currentTextChanged.connect(self._update_selected_cable)
        self.sel_fixed_length = QDoubleSpinBox()
        self.sel_fixed_length.setRange(0.0, 100000.0)
        self.sel_fixed_length.valueChanged.connect(self._update_selected_cable)
        self.sel_total_length = QLabel("-")
        self.sel_segment_lengths = QLabel("-")
        self.sel_segment_lengths.setWordWrap(True)
        self.sel_bend_radii = QLineEdit()
        self.sel_bend_radii.editingFinished.connect(self._update_selected_cable)

        selected_form.addRow("Selected type", self.sel_cable_type)
        selected_form.addRow("Selected label", self.sel_cable_label)
        selected_form.addRow("Selected tag", self.sel_cable_tag)
        selected_form.addRow("Selected comment", self.sel_cable_comment)
        selected_form.addRow("Selected diameter (mm)", self.sel_cable_diameter)
        selected_form.addRow("Length mode", self.sel_length_mode)
        selected_form.addRow("Fixed length (m)", self.sel_fixed_length)
        selected_form.addRow("Bend radii (m, CSV)", self.sel_bend_radii)
        selected_form.addRow("Total length (m)", self.sel_total_length)
        selected_form.addRow("Segment lengths (m)", self.sel_segment_lengths)
        layout.addLayout(selected_form)

        layout.addStretch(1)
        return tab

    def _set_status(self, message: str) -> None:
        if self.statusBar() is not None:
            self.statusBar().showMessage(message)

    def _configure_input_direction(self) -> None:
        line_edits = (
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
        )
        for widget in line_edits:
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
        room_name = self.new_room_name.text().strip() or generate_default_room_name(self.data.rooms)
        room = create_room(
            name=room_name,
            width_meters=self.new_room_width.value(),
            height_meters=self.new_room_height.value(),
            building=self.new_room_building.text().strip(),
            floor=self.new_room_floor.text().strip(),
        )
        self.data.rooms.append(room)
        self.data.active_room_id = room.id
        self.new_room_name.setText(generate_default_room_name(self.data.rooms))
        self.new_room_building.clear()
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

        if self.data.rooms and not self.new_room_name.text().strip():
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
