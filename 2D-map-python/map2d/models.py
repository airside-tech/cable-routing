from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Sequence
import uuid

from .geometry import CABLE_TYPE_COLORS, round_coord

CableType = Literal["network", "power230", "power400", "fiber"]
ShapeType = Literal["square", "rectangle", "circle"]
LengthMode = Literal["dynamic", "fixed"]


def make_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@dataclass
class Point:
    x: float
    y: float

    def to_dict(self) -> dict[str, float]:
        return {
            "x": round_coord(self.x),
            "y": round_coord(self.y),
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "Point":
        return Point(
            x=float(value["x"]),
            y=float(value["y"]),
        )


@dataclass
class RoomPoint(Point):
    room_id: str

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["roomId"] = self.room_id
        return payload

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "RoomPoint":
        return RoomPoint(
            x=float(value["x"]),
            y=float(value["y"]),
            room_id=str(value["roomId"]),
        )


@dataclass
class DividerWallSegment:
    from_point: Point
    to_point: Point

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.from_point.to_dict(),
            "to": self.to_point.to_dict(),
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "DividerWallSegment":
        return DividerWallSegment(
            from_point=Point.from_dict(value["from"]),
            to_point=Point.from_dict(value["to"]),
        )


def generate_default_room_name(existing_rooms: Sequence["RoomModel"] | None = None, *, prefix: str = "Room") -> str:
    used_names = {room.name.strip() for room in (existing_rooms or []) if room.name.strip()}
    for letter_index in range(1, 27):
        candidate = f"{prefix} {chr(64 + letter_index)}"
        if candidate not in used_names:
            return candidate
    for number in range(1, 1000):
        candidate = f"{prefix} {number}"
        if candidate not in used_names:
            return candidate
    return f"{prefix} 1"


@dataclass
class RoomModel:
    id: str
    name: str
    width_meters: float
    height_meters: float
    wall_points: list[Point]
    divider_walls: list[DividerWallSegment] = field(default_factory=list)
    grid_size_meters: float = 1.0
    background: str = "#f4f5f7"
    building: str = ""
    floor: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "building": self.building,
            "floor": self.floor,
            "widthMeters": round_coord(self.width_meters),
            "heightMeters": round_coord(self.height_meters),
            "wallPoints": [point.to_dict() for point in self.wall_points],
            "dividerWalls": [wall.to_dict() for wall in self.divider_walls],
            "gridSizeMeters": round_coord(self.grid_size_meters),
            "background": self.background,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "RoomModel":
        return RoomModel(
            id=str(value["id"]),
            name=str(value["name"]),
            width_meters=float(value["widthMeters"]),
            height_meters=float(value["heightMeters"]),
            wall_points=[Point.from_dict(item) for item in value["wallPoints"]],
            divider_walls=[DividerWallSegment.from_dict(item) for item in value.get("dividerWalls", [])],
            grid_size_meters=float(value.get("gridSizeMeters", 1.0)),
            background=str(value.get("background", "#f4f5f7")),
            building=str(value.get("building", "")),
            floor=str(value.get("floor", "")),
        )


@dataclass
class ObjectModel:
    id: str
    room_id: str
    shape: ShapeType
    x: float
    y: float
    width: float
    height: float
    label: str = ""
    name: str = ""
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "roomId": self.room_id,
            "shape": self.shape,
            "x": round_coord(self.x),
            "y": round_coord(self.y),
            "width": round_coord(self.width),
            "height": round_coord(self.height),
            "label": self.label,
            "name": self.name,
            "comment": self.comment,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "ObjectModel":
        return ObjectModel(
            id=str(value["id"]),
            room_id=str(value["roomId"]),
            shape=value["shape"],
            x=float(value["x"]),
            y=float(value["y"]),
            width=float(value["width"]),
            height=float(value["height"]),
            label=str(value.get("label", "")),
            name=str(value.get("name", "")),
            comment=str(value.get("comment", "")),
        )


@dataclass
class CableModel:
    id: str
    label: str
    tag: str
    comment: str
    type: CableType
    diameter_mm: float
    color: str
    points: list[RoomPoint]
    bend_radius_meters: list[float]
    length_mode: LengthMode = "dynamic"
    fixed_length_meters: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "tag": self.tag,
            "comment": self.comment,
            "type": self.type,
            "diameterMm": round_coord(self.diameter_mm),
            "color": self.color,
            "points": [point.to_dict() for point in self.points],
            "bendRadiusMeters": [round_coord(value) for value in self.bend_radius_meters],
            "lengthMode": self.length_mode,
            "fixedLengthMeters": None if self.fixed_length_meters is None else round_coord(self.fixed_length_meters),
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "CableModel":
        cable_type = str(value["type"])
        fallback_color = CABLE_TYPE_COLORS.get(cable_type, "#777777")
        return CableModel(
            id=str(value["id"]),
            label=str(value.get("label", "")),
            tag=str(value.get("tag", "")),
            comment=str(value.get("comment", "")),
            type=cable_type,  # type: ignore[assignment]
            diameter_mm=float(value.get("diameterMm", 10.0)),
            color=str(value.get("color", fallback_color)),
            points=[RoomPoint.from_dict(item) for item in value.get("points", [])],
            bend_radius_meters=[float(item) for item in value.get("bendRadiusMeters", [])],
            length_mode=str(value.get("lengthMode", "dynamic")),  # type: ignore[assignment]
            fixed_length_meters=(
                None
                if value.get("fixedLengthMeters") is None
                else float(value["fixedLengthMeters"])
            ),
        )


@dataclass
class EditorData:
    version: int
    rooms: list[RoomModel]
    objects: list[ObjectModel]
    cables: list[CableModel]
    active_room_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "rooms": [room.to_dict() for room in self.rooms],
            "objects": [obj.to_dict() for obj in self.objects],
            "cables": [cable.to_dict() for cable in self.cables],
            "activeRoomId": self.active_room_id,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> "EditorData":
        return EditorData(
            version=int(value.get("version", 1)),
            rooms=[RoomModel.from_dict(item) for item in value.get("rooms", [])],
            objects=[ObjectModel.from_dict(item) for item in value.get("objects", [])],
            cables=[CableModel.from_dict(item) for item in value.get("cables", [])],
            active_room_id=value.get("activeRoomId"),
        )


def create_room(
    name: str,
    width_meters: float,
    height_meters: float,
    *,
    building: str = "",
    floor: str = "",
) -> RoomModel:
    return RoomModel(
        id=make_id("room"),
        name=name.strip() or "Room",
        width_meters=round_coord(width_meters),
        height_meters=round_coord(height_meters),
        wall_points=[
            Point(0, 0),
            Point(width_meters, 0),
            Point(width_meters, height_meters),
            Point(0, height_meters),
        ],
        divider_walls=[],
        grid_size_meters=1.0,
        background="#f4f5f7",
        building=building.strip(),
        floor=floor.strip(),
    )


def create_initial_data() -> EditorData:
    first_room = create_room("Room A", 8, 6)
    return EditorData(
        version=1,
        rooms=[first_room],
        objects=[],
        cables=[],
        active_room_id=first_room.id,
    )


def create_object(shape: ShapeType, room_id: str, x: float, y: float) -> ObjectModel:
    if shape == "square":
        width = 1.0
        height = 1.0
    elif shape == "rectangle":
        width = 1.6
        height = 1.0
    else:
        width = 1.0
        height = 1.0

    return ObjectModel(
        id=make_id("obj"),
        room_id=room_id,
        shape=shape,
        x=round_coord(x),
        y=round_coord(y),
        width=width,
        height=height,
    )


def create_cable(
    cable_type: CableType,
    label: str,
    tag: str,
    comment: str,
    diameter_mm: float,
    points: list[RoomPoint],
) -> CableModel:
    return CableModel(
        id=make_id("cable"),
        label=label,
        tag=tag,
        comment=comment,
        type=cable_type,
        diameter_mm=diameter_mm,
        color=CABLE_TYPE_COLORS[cable_type],
        points=points,
        bend_radius_meters=[0.0 for _ in range(max(0, len(points) - 2))],
        length_mode="dynamic",
        fixed_length_meters=None,
    )
