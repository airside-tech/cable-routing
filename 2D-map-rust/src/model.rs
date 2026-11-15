use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, PartialEq, Serialize, Deserialize)]
pub struct Point {
    pub x: f32,
    pub y: f32,
}

impl Point {
    pub fn new(x: f32, y: f32) -> Self {
        Self { x, y }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
pub enum ObjectKind {
    Rectangle,
    Circle,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Room {
    pub id: String,
    pub name: String,
    pub width: f32,
    pub height: f32,
    pub background: [u8; 3],
    pub grid_size: f32,
    pub wall_points: Vec<Point>,
}

impl Room {
    pub fn new(name: &str, width: f32, height: f32) -> Self {
        Self {
            id: format!("room-{name}"),
            name: name.to_owned(),
            width,
            height,
            background: [244, 245, 247],
            grid_size: 1.0,
            wall_points: vec![
                Point::new(0.0, 0.0),
                Point::new(width, 0.0),
                Point::new(width, height),
                Point::new(0.0, height),
            ],
        }
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct MapObject {
    pub id: String,
    pub room_id: String,
    pub kind: ObjectKind,
    pub x: f32,
    pub y: f32,
    pub width: f32,
    pub height: f32,
    pub label: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Cable {
    pub id: String,
    pub room_id: String,
    pub points: Vec<Point>,
    pub color: [u8; 3],
    pub label: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct EditorData {
    pub rooms: Vec<Room>,
    pub objects: Vec<MapObject>,
    pub cables: Vec<Cable>,
    pub active_room: usize,
}

impl EditorData {
    pub fn active_room(&self) -> Option<&Room> {
        self.rooms.get(self.active_room)
    }
}
