from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import CableModel, Point, RoomPoint

COORD_PRECISION = 2

CABLE_TYPE_COLORS = {
    "network": "#777777",
    "power230": "#111111",
    "power400": "#111111",
    "fiber": "#b8860b",
}


def round_to(value: float, precision: int) -> float:
    factor = 10**precision
    return round(value * factor) / factor


def round_coord(value: float) -> float:
    return round_to(value, COORD_PRECISION)


def distance(a: Point, b: Point) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def snap(value: float, grid: float) -> float:
    if grid <= 0:
        return value
    return round(value / grid) * grid


def cable_segment_length_meters(a: RoomPoint, b: RoomPoint) -> float:
    if a.room_id != b.room_id:
        return 0.0
    return distance(a, b)


def cable_length_meters(cable: CableModel) -> float:
    if cable.length_mode == "fixed" and cable.fixed_length_meters is not None:
        return cable.fixed_length_meters
    total = 0.0
    for index in range(1, len(cable.points)):
        total += cable_segment_length_meters(cable.points[index - 1], cable.points[index])
    return round_coord(total)


def polyline_length_meters(points: list[RoomPoint]) -> float:
    total = 0.0
    for index in range(1, len(points)):
        total += cable_segment_length_meters(points[index - 1], points[index])
    return round_coord(total)


def point_to_segment_distance(target: Point, a: Point, b: Point) -> float:
    dx = b.x - a.x
    dy = b.y - a.y
    denominator = dx * dx + dy * dy
    if denominator <= 0:
        return distance(target, a)

    t = clamp(((target.x - a.x) * dx + (target.y - a.y) * dy) / denominator, 0.0, 1.0)
    projection_x = a.x + dx * t
    projection_y = a.y + dy * t
    return math.hypot(target.x - projection_x, target.y - projection_y)
