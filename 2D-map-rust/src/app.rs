use eframe::egui::{
    Align2, CentralPanel, Color32, Context, DragValue, FontId, Pos2, Rect, Sense, SidePanel,
    Stroke, StrokeKind, Ui, Vec2, pos2, vec2,
};

use crate::geometry::{clamp, round};
use crate::model::{Cable, EditorData, MapObject, ObjectKind, Point, Room};

#[derive(Clone, Debug)]
enum DragMode {
    Object {
        object_index: usize,
        original: Point,
        start_room_point: Point,
    },
    CablePoint {
        cable_index: usize,
        point_index: usize,
        last_room_point: Point,
    },
}

#[derive(Clone, Debug)]
struct DragState {
    mode: DragMode,
}

// Calculates the closest distance from a pointer to a cable segment so clicks can select a line reliably.
fn distance_to_segment(point: Pos2, start: Pos2, end: Pos2) -> f32 {
    let dx = end.x - start.x;
    let dy = end.y - start.y;

    if dx == 0.0 && dy == 0.0 {
        return (point - start).length();
    }

    let projection = ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy);
    let clamped = projection.clamp(0.0, 1.0);
    let closest = Pos2::new(start.x + clamped * dx, start.y + clamped * dy);
    (point - closest).length()
}

pub struct CableMapApp {
    data: EditorData,
    selected_object: Option<usize>,
    selected_cable: Option<usize>,
    cable_mode: bool,
    draft_cable: Vec<Point>,
    status: String,
    drag_state: Option<DragState>,
    show_grid: bool,
}

impl Default for CableMapApp {
    // Creates the default editor state with one room and a blank canvas ready for editing.
    fn default() -> Self {
        let mut data = EditorData::default();
        data.rooms.push(Room::new("Room A", 10.0, 7.0));
        data.active_room = 0;

        Self {
            data,
            selected_object: None,
            selected_cable: None,
            cable_mode: false,
            draft_cable: Vec::new(),
            status: "Ready".to_owned(),
            drag_state: None,
            show_grid: true,
        }
    }
}

impl CableMapApp {
    // Clears the current selection so the properties pane falls back to the active room.
    fn clear_selection(&mut self) {
        self.selected_object = None;
        self.selected_cable = None;
    }

    // Returns the active room name for status text and UI feedback.
    fn active_room_name(&self) -> String {
        self.data
            .active_room()
            .map(|room| room.name.clone())
            .unwrap_or_else(|| "No room".to_owned())
    }

    // Adds a new room and makes it the active editing context.
    fn add_room(&mut self) {
        let idx = self.data.rooms.len() + 1;
        let room = Room::new(&format!("Room {idx}"), 8.0 + idx as f32, 6.0 + idx as f32 * 0.5);
        self.data.rooms.push(room);
        self.data.active_room = self.data.rooms.len() - 1;
        self.clear_selection();
        self.status = format!("Created {}", self.active_room_name());
    }

    // Creates a new rectangle or circle object centered in the current room.
    fn add_object(&mut self, kind: ObjectKind) {
        let Some(room) = self.data.active_room().cloned() else {
            return;
        };

        let width = if matches!(kind, ObjectKind::Circle) { 1.6 } else { 2.0 };
        let height = if matches!(kind, ObjectKind::Circle) { 1.6 } else { 1.0 };

        let object = MapObject {
            id: format!("obj-{}", self.data.objects.len() + 1),
            room_id: room.id.clone(),
            kind,
            x: (room.width - width) / 2.0,
            y: (room.height - height) / 2.0,
            width,
            height,
            label: format!("{kind:?}"),
        };

        self.data.objects.push(object);
        self.selected_object = Some(self.data.objects.len() - 1);
        self.selected_cable = None;
        self.status = format!("Added {kind:?}");
    }

    // Enables or disables cable creation mode and resets the draft line.
    fn toggle_cable_mode(&mut self) {
        self.cable_mode = !self.cable_mode;
        if self.cable_mode {
            self.draft_cable.clear();
            self.clear_selection();
            self.status = "Cable placement started. Click to add points.".to_owned();
        } else {
            self.draft_cable.clear();
            self.status = "Cable placement canceled.".to_owned();
        }
    }

    // Converts the draft wire points into a saved cable once enough points exist.
    fn finish_cable(&mut self) {
        if self.draft_cable.len() < 2 {
            self.status = "A cable needs at least two points.".to_owned();
            return;
        }

        let room = self
            .data
            .active_room()
            .cloned()
            .unwrap_or_else(|| Room::new("Room", 1.0, 1.0));

        let cable = Cable {
            id: format!("cable-{}", self.data.cables.len() + 1),
            room_id: room.id,
            points: self.draft_cable.clone(),
            color: [88, 142, 255],
            label: format!("Cable {}", self.data.cables.len() + 1),
        };

        self.data.cables.push(cable);
        self.selected_cable = Some(self.data.cables.len() - 1);
        self.selected_object = None;
        self.draft_cable.clear();
        self.cable_mode = false;
        self.status = "Cable created.".to_owned();
    }

    // Maps the active room into the visible canvas area while preserving a consistent scale.
    fn room_rect_from_canvas(&self, rect: Rect) -> Rect {
        let Some(room) = self.data.active_room() else {
            return rect;
        };

        let padding = 24.0;
        let max_dim = room.width.max(room.height).max(1.0);
        let scale = (rect.width().min(rect.height()) - padding * 2.0) / max_dim;
        let size = Vec2::new(room.width * scale, room.height * scale);
        Rect::from_min_size(rect.min + vec2(padding, padding), size)
    }

    // Converts a canvas click into room coordinates so interaction matches the 2D plan.
    fn canvas_to_room_point(&self, pointer: Pos2, rect: Rect) -> Option<Point> {
        let room = self.data.active_room()?;
        let room_rect = self.room_rect_from_canvas(rect);
        let width = room_rect.width().max(1.0);
        let height = room_rect.height().max(1.0);

        let x = ((pointer.x - room_rect.min.x) / width * room.width).clamp(0.0, room.width);
        let y = ((pointer.y - room_rect.min.y) / height * room.height).clamp(0.0, room.height);

        Some(Point::new(round(x), round(y)))
    }

    // Converts a room point into the actual painter position used to draw the room.
    fn room_to_canvas_point(&self, room: &Room, point: Point, rect: Rect) -> Pos2 {
        let room_rect = self.room_rect_from_canvas(rect);
        let scale_x = room_rect.width() / room.width.max(1.0);
        let scale_y = room_rect.height() / room.height.max(1.0);

        pos2(
            room_rect.min.x + point.x * scale_x,
            room_rect.min.y + point.y * scale_y,
        )
    }

    // Finds the object under the pointer so it can be selected or dragged.
    fn object_hit_test(&self, pointer: Pos2, rect: Rect) -> Option<usize> {
        let room = self.data.active_room()?;
        let room_rect = self.room_rect_from_canvas(rect);
        let scale_x = room_rect.width() / room.width.max(1.0);
        let scale_y = room_rect.height() / room.height.max(1.0);

        for (index, object) in self.data.objects.iter().enumerate() {
            if object.room_id != room.id {
                continue;
            }

            let left = room_rect.min.x + object.x * scale_x;
            let top = room_rect.min.y + object.y * scale_y;
            let right = left + object.width * scale_x;
            let bottom = top + object.height * scale_y;
            let hit_rect = Rect::from_min_max(Pos2::new(left, top), Pos2::new(right, bottom));

            if hit_rect.contains(pointer) {
                return Some(index);
            }
        }

        None
    }

    // Finds the cable nearest to the pointer so the user can select it on the map.
    fn cable_hit_test(&self, pointer: Pos2, rect: Rect) -> Option<usize> {
        let room = self.data.active_room()?;

        for (index, cable) in self.data.cables.iter().enumerate() {
            if cable.room_id != room.id || cable.points.len() < 2 {
                continue;
            }

            let mut previous = self.room_to_canvas_point(room, cable.points[0], rect);
            for point in cable.points.iter().skip(1) {
                let current = self.room_to_canvas_point(room, *point, rect);
                if distance_to_segment(pointer, previous, current) <= 8.0 {
                    return Some(index);
                }
                previous = current;
            }
        }

        None
    }

    fn cable_point_hit_test(&self, pointer: Pos2, rect: Rect) -> Option<(usize, usize)> {
        let room = self.data.active_room()?;

        for (cable_index, cable) in self.data.cables.iter().enumerate() {
            if cable.room_id != room.id {
                continue;
            }

            for (point_index, point) in cable.points.iter().enumerate() {
                let pos = self.room_to_canvas_point(room, *point, rect);
                let distance = (pointer - pos).length();
                if distance <= 12.0 {
                    return Some((cable_index, point_index));
                }
            }
        }

        None
    }

    // Paints the base room color and border so the map surface is visible and bounded.
    fn draw_room_background(&self, painter: &eframe::egui::Painter, room: &Room, room_rect: Rect) {
        painter.rect_filled(
            room_rect,
            0.0,
            Color32::from_rgb(room.background[0], room.background[1], room.background[2]),
        );
        painter.rect_stroke(
            room_rect,
            0.0,
            Stroke::new(2.0_f32, Color32::from_rgb(80, 88, 100)),
            StrokeKind::Inside,
        );
    }

    // Draws the visible grid to help align objects and room dimensions.
    fn draw_room_grid(&self, painter: &eframe::egui::Painter, room: &Room, room_rect: Rect) {
        if !self.show_grid {
            return;
        }

        let step = room.grid_size.max(0.1);
        let px_step_x = room_rect.width() / room.width.max(1.0) * step;
        let px_step_y = room_rect.height() / room.height.max(1.0) * step;

        for i in 0..=((room.width / step).ceil() as i32) {
            let x = room_rect.min.x + i as f32 * px_step_x;
            painter.vline(
                x,
                eframe::egui::Rangef::new(room_rect.min.y, room_rect.max.y),
                Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(0, 0, 0, 18)),
            );
        }

        for i in 0..=((room.height / step).ceil() as i32) {
            let y = room_rect.min.y + i as f32 * px_step_y;
            painter.hline(
                eframe::egui::Rangef::new(room_rect.min.x, room_rect.max.x),
                y,
                Stroke::new(1.0_f32, Color32::from_rgba_unmultiplied(0, 0, 0, 18)),
            );
        }
    }

    // Renders any wall outline points as a line around the room perimeter.
    fn draw_wall_outline(&self, painter: &eframe::egui::Painter, room: &Room, rect: Rect) {
        let wall_points: Vec<Pos2> = room
            .wall_points
            .iter()
            .map(|point| self.room_to_canvas_point(room, *point, rect))
            .collect();

        if wall_points.len() >= 2 {
            painter.add(eframe::egui::Shape::line(
                wall_points,
                Stroke::new(2.0_f32, Color32::WHITE),
            ));
        }
    }

    // Draws one cable and highlights it if it is the current selection.
    fn draw_cable(&self, painter: &eframe::egui::Painter, room: &Room, rect: Rect, cable: &Cable) {
        if cable.room_id != room.id || cable.points.len() < 2 {
            return;
        }

        let points: Vec<Pos2> = cable
            .points
            .iter()
            .map(|point| self.room_to_canvas_point(room, *point, rect))
            .collect();

        let selected = self.selected_cable == Some(
            self.data
                .cables
                .iter()
                .position(|item| item.id == cable.id)
                .unwrap_or(usize::MAX),
        );

        painter.add(eframe::egui::Shape::line(
            points.clone(),
            Stroke::new(
                if selected { 3.0_f32 } else { 2.0_f32 },
                Color32::from_rgb(cable.color[0], cable.color[1], cable.color[2]),
            ),
        ));

        for point in points {
            painter.circle_filled(
                point,
                if selected { 4.0_f32 } else { 3.0_f32 },
                Color32::from_rgb(cable.color[0], cable.color[1], cable.color[2]),
            );
        }
    }

    // Draws all cables assigned to the active room.
    fn draw_cables(&self, painter: &eframe::egui::Painter, room: &Room, rect: Rect) {
        for cable in &self.data.cables {
            if cable.room_id == room.id {
                self.draw_cable(painter, room, rect, cable);
            }
        }
    }

    // Draws one item in the room and adds a highlight border when selected.
    fn draw_object(
        &self,
        painter: &eframe::egui::Painter,
        room: &Room,
        room_rect: Rect,
        index: usize,
        object: &MapObject,
    ) {
        let scale_x = room_rect.width() / room.width.max(1.0);
        let scale_y = room_rect.height() / room.height.max(1.0);
        let left = room_rect.min.x + object.x * scale_x;
        let top = room_rect.min.y + object.y * scale_y;
        let width = object.width * scale_x;
        let height = object.height * scale_y;
        let bounds = Rect::from_min_size(Pos2::new(left, top), Vec2::new(width, height));

        let fill = match object.kind {
            ObjectKind::Rectangle => Color32::from_rgb(88, 130, 255),
            ObjectKind::Circle => Color32::from_rgb(58, 176, 173),
        };
        let selected = self.selected_object == Some(index);

        if matches!(object.kind, ObjectKind::Circle) {
            let center = Pos2::new(left + width / 2.0, top + height / 2.0);
            painter.circle_filled(center, width.min(height) / 2.0, fill);
            if selected {
                painter.circle_stroke(center, width.min(height) / 2.0, Stroke::new(2.5_f32, Color32::WHITE));
            }
        } else {
            painter.rect_filled(bounds, 4.0, fill);
            if selected {
                painter.rect_stroke(
                    bounds,
                    4.0,
                    Stroke::new(2.5_f32, Color32::WHITE),
                    StrokeKind::Inside,
                );
            }
        }

        painter.text(
            Pos2::new(bounds.left() + 6.0, bounds.top() + 6.0),
            Align2::LEFT_TOP,
            &object.label,
            FontId::proportional(10.0),
            Color32::WHITE,
        );
    }

    // Shows the in-progress cable points while the user is placing a new cable.
    fn draw_draft_points(&self, painter: &eframe::egui::Painter, room: &Room, rect: Rect) {
        for point in &self.draft_cable {
            let pos = self.room_to_canvas_point(room, *point, rect);
            painter.circle_filled(pos, 3.5, Color32::from_rgb(255, 196, 83));
        }
    }

    // Draws the active room, including background, grid, walls, cables, and objects.
    fn draw_room(&self, ui: &mut Ui, rect: Rect) {
        let Some(room) = self.data.active_room() else {
            return;
        };
        let painter = ui.painter();
        let room_rect = self.room_rect_from_canvas(rect);

        self.draw_room_background(painter, room, room_rect);
        self.draw_room_grid(painter, room, room_rect);
        self.draw_wall_outline(painter, room, rect);
        self.draw_cables(painter, room, rect);

        for (index, object) in self.data.objects.iter().enumerate() {
            if object.room_id == room.id {
                self.draw_object(painter, room, room_rect, index, object);
            }
        }

        self.draw_draft_points(painter, room, rect);
    }

    // Renders the room controls: add a room and switch between existing rooms.
    fn render_room_tools(&mut self, ui: &mut Ui) {
        ui.group(|ui| {
            ui.label("Rooms");
            ui.horizontal(|ui| {
                if ui.button("Add room").clicked() {
                    self.add_room();
                }
            });
        });

        ui.separator();
        ui.label("Rooms");
        ui.horizontal_wrapped(|ui| {
            for index in 0..self.data.rooms.len() {
                let room_name = self.data.rooms[index].name.clone();
                let active = index == self.data.active_room;
                if ui.selectable_label(active, room_name).clicked() {
                    self.data.active_room = index;
                    self.clear_selection();
                    self.status = format!("Active room: {}", self.data.rooms[index].name);
                }
            }
        });
    }

    // Renders the object creation buttons for the simple editor tools.
    fn render_object_tools(&mut self, ui: &mut Ui) {
        ui.group(|ui| {
            ui.label("Objects");
            ui.horizontal(|ui| {
                if ui.button("Rect").clicked() {
                    self.add_object(ObjectKind::Rectangle);
                }
                if ui.button("Circle").clicked() {
                    self.add_object(ObjectKind::Circle);
                }
            });
        });
    }

    // Renders the cable creation controls and cancel/finish actions.
    fn render_cable_tools(&mut self, ui: &mut Ui) {
        ui.group(|ui| {
            ui.label("Cables");
            if ui.button(if self.cable_mode { "Finish cable" } else { "Add cable" }).clicked() {
                if self.cable_mode {
                    self.finish_cable();
                } else {
                    self.toggle_cable_mode();
                }
            }

            if self.cable_mode && ui.button("Cancel").clicked() {
                self.toggle_cable_mode();
            }
        });
    }

    // Builds the left-side toolbar grouping all room, object, and cable controls.
    fn render_toolbar(&mut self, ui: &mut Ui) {
        ui.heading("2D Cable Planning Map");
        ui.small(&self.status);
        ui.separator();

        self.render_room_tools(ui);
        ui.separator();
        self.render_object_tools(ui);
        ui.separator();
        self.render_cable_tools(ui);
        ui.separator();
        ui.checkbox(&mut self.show_grid, "Show grid");
    }

    // Shows the editable fields for the active room such as name, size, and grid spacing.
    fn render_room_properties(&mut self, ui: &mut Ui) {
        let Some(room_index) = self.data.active_room().map(|_| self.data.active_room) else {
            ui.label("No active room");
            return;
        };

        ui.heading("Room properties");
        ui.horizontal(|ui| {
            ui.label("Name");
            ui.text_edit_singleline(&mut self.data.rooms[room_index].name);
        });
        ui.add(
            DragValue::new(&mut self.data.rooms[room_index].width)
                .speed(0.1)
                .prefix("W: "),
        );
        ui.add(
            DragValue::new(&mut self.data.rooms[room_index].height)
                .speed(0.1)
                .prefix("H: "),
        );
        ui.add(
            DragValue::new(&mut self.data.rooms[room_index].grid_size)
                .speed(0.05)
                .range(0.1..=10.0)
                .prefix("Grid: "),
        );

        ui.separator();
        ui.label(format!("ID: {}", self.data.rooms[room_index].id));
        ui.label(format!(
            "Dimensions: {:.1} x {:.1}",
            self.data.rooms[room_index].width,
            self.data.rooms[room_index].height
        ));
    }

    // Shows and updates the selected object’s editable position and size values.
    fn render_object_properties(&mut self, ui: &mut Ui) {
        let Some(index) = self.selected_object else {
            return;
        };

        let (room_width, room_height) = {
            let room = self.data.active_room();
            (
                room.map(|r| r.width).unwrap_or(0.0),
                room.map(|r| r.height).unwrap_or(0.0),
            )
        };

        let Some(object) = self.data.objects.get_mut(index) else {
            return;
        };

        ui.heading("Object properties");
        ui.horizontal(|ui| {
            ui.label("Label");
            ui.text_edit_singleline(&mut object.label);
        });
        ui.add(DragValue::new(&mut object.x).speed(0.05).prefix("X: "));
        ui.add(DragValue::new(&mut object.y).speed(0.05).prefix("Y: "));
        ui.add(DragValue::new(&mut object.width).speed(0.05).prefix("W: "));
        ui.add(DragValue::new(&mut object.height).speed(0.05).prefix("H: "));

        object.x = clamp(object.x, 0.0, room_width.max(0.0) - object.width.max(0.0));
        object.y = clamp(object.y, 0.0, room_height.max(0.0) - object.height.max(0.0));
    }

    // Shows the selected cable metadata and a few simple editable fields.
    fn render_cable_properties(&mut self, ui: &mut Ui) {
        let Some(index) = self.selected_cable else {
            return;
        };
        let Some(cable) = self.data.cables.get_mut(index) else {
            return;
        };

        ui.heading("Cable properties");
        ui.horizontal(|ui| {
            ui.label("Label");
            ui.text_edit_singleline(&mut cable.label);
        });
        ui.label(format!("Points: {}", cable.points.len()));
        ui.label(format!("Color: {:?}", cable.color));
    }

    // Chooses which properties group to show based on the current selection.
    fn render_properties_panel(&mut self, ui: &mut Ui) {
        ui.heading("Properties");
        ui.separator();

        if self.selected_object.is_some() {
            self.render_object_properties(ui);
        } else if self.selected_cable.is_some() {
            self.render_cable_properties(ui);
        } else {
            self.render_room_properties(ui);
        }
    }

    // Marks an object as selected and updates the status text for user feedback.
    fn select_object(&mut self, index: usize) {
        self.selected_object = Some(index);
        self.selected_cable = None;
        self.status = format!("Selected {}", self.data.objects[index].label);
    }

    // Marks a cable as selected and clears object selection so the pane shows the right details.
    fn select_cable(&mut self, index: usize) {
        self.selected_cable = Some(index);
        self.selected_object = None;
        self.status = format!("Selected {}", self.data.cables[index].label);
    }

    // Moves a selected object or cable point as the pointer drags across the room.
    fn handle_drag(&mut self, pointer: Pos2, rect: Rect) {
        let Some(room_point) = self.canvas_to_room_point(pointer, rect) else {
            return;
        };

        let Some(drag_state) = self.drag_state.as_mut() else {
            return;
        };

        match &mut drag_state.mode {
            DragMode::Object {
                object_index,
                original,
                start_room_point,
            } => {
                let room = self
                    .data
                    .active_room()
                    .cloned()
                    .unwrap_or_else(|| Room::new("Room", 10.0, 10.0));
                let object = &mut self.data.objects[*object_index];
                let delta_x = room_point.x - start_room_point.x;
                let delta_y = room_point.y - start_room_point.y;

                object.x = clamp(original.x + delta_x, 0.0, room.width - object.width);
                object.y = clamp(original.y + delta_y, 0.0, room.height - object.height);
            }
            DragMode::CablePoint {
                cable_index,
                point_index,
                last_room_point,
            } => {
                let room = self
                    .data
                    .active_room()
                    .cloned()
                    .unwrap_or_else(|| Room::new("Room", 10.0, 10.0));
                let cable = &mut self.data.cables[*cable_index];
                cable.points[*point_index].x = clamp(room_point.x, 0.0, room.width);
                cable.points[*point_index].y = clamp(room_point.y, 0.0, room.height);
                *last_room_point = room_point;
            }
        }
    }

    // Starts a drag session for the object under the pointer and records its starting position.
    fn start_object_drag(&mut self, pointer: Pos2, rect: Rect) {
        if self.cable_mode {
            if let Some(point) = self.canvas_to_room_point(pointer, rect) {
                self.draft_cable.push(point);
                self.status = format!("Cable point {} added.", self.draft_cable.len());
            }
            return;
        }

        let Some(object_index) = self.object_hit_test(pointer, rect) else {
            self.clear_selection();
            return;
        };

        let point = self.canvas_to_room_point(pointer, rect).unwrap_or(Point::new(0.0, 0.0));
        self.selected_object = Some(object_index);
        self.selected_cable = None;
        self.drag_state = Some(DragState {
            mode: DragMode::Object {
                object_index,
                original: Point::new(self.data.objects[object_index].x, self.data.objects[object_index].y),
                start_room_point: point,
            },
        });
    }

    // Starts dragging a specific cable point for direct point editing.
    fn start_cable_point_drag(&mut self, pointer: Pos2, rect: Rect) {
        let Some((cable_index, point_index)) = self.cable_point_hit_test(pointer, rect) else {
            return;
        };

        let point = self.canvas_to_room_point(pointer, rect).unwrap_or(Point::new(0.0, 0.0));
        self.selected_cable = Some(cable_index);
        self.selected_object = None;
        self.drag_state = Some(DragState {
            mode: DragMode::CablePoint {
                cable_index,
                point_index,
                last_room_point: point,
            },
        });
    }

    // Handles clicks, selection, and dragging for the main canvas.
    fn handle_canvas_input(&mut self, response: &eframe::egui::Response) {
        let Some(pointer) = response.interact_pointer_pos().or(response.hover_pos()) else {
            return;
        };

        if response.drag_stopped() {
            self.drag_state = None;
        }

        if self.cable_mode {
            if response.clicked() {
                if let Some(point) = self.canvas_to_room_point(pointer, response.rect) {
                    self.draft_cable.push(point);
                    self.status = format!("Cable point {} added.", self.draft_cable.len());
                }
            }
            return;
        }

        if self.drag_state.is_some() {
            if response.dragged() {
                self.handle_drag(pointer, response.rect);
            }
            return;
        }

        if response.dragged() {
            if let Some((cable_index, point_index)) = self.cable_point_hit_test(pointer, response.rect) {
                self.start_cable_point_drag(pointer, response.rect);
                self.selected_cable = Some(cable_index);
                self.selected_object = None;
                self.status = format!(
                    "Editing cable point {} on {}",
                    point_index + 1,
                    self.data.cables[cable_index].label
                );
                return;
            }

            if let Some(object_index) = self.object_hit_test(pointer, response.rect) {
                self.start_object_drag(pointer, response.rect);
                self.selected_object = Some(object_index);
                return;
            }

            return;
        }

        if response.clicked() {
            if let Some((cable_index, point_index)) = self.cable_point_hit_test(pointer, response.rect) {
                self.start_cable_point_drag(pointer, response.rect);
                self.status = format!(
                    "Editing cable point {} on {}",
                    point_index + 1,
                    self.data.cables[cable_index].label
                );
                return;
            }

            if let Some(object_index) = self.object_hit_test(pointer, response.rect) {
                self.select_object(object_index);
                self.start_object_drag(pointer, response.rect);
                return;
            }

            if let Some(cable_index) = self.cable_hit_test(pointer, response.rect) {
                self.select_cable(cable_index);
                return;
            }

            self.clear_selection();
            self.drag_state = None;
        }
    }
}

impl eframe::App for CableMapApp {
    // Builds the full window layout with left toolbar, right properties pane, and the central map canvas.
    fn update(&mut self, ctx: &Context, _frame: &mut eframe::Frame) {
        SidePanel::left("sidebar")
            .default_width(280.0)
            .show(ctx, |ui| self.render_toolbar(ui));

        SidePanel::right("properties")
            .default_width(260.0)
            .show(ctx, |ui| self.render_properties_panel(ui));

        CentralPanel::default().show(ctx, |ui| {
            let response = ui.allocate_rect(ui.max_rect(), Sense::click_and_drag());
            self.handle_canvas_input(&response);
            self.draw_room(ui, response.rect);
        });
    }
}
