from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QWidget

from .geometry import CABLE_TYPE_COLORS, clamp, point_to_segment_distance, round_coord
from .models import (
    CableModel,
    DividerWallSegment,
    EditorData,
    ObjectModel,
    Point,
    RoomModel,
    RoomPoint,
    create_cable,
    create_object,
)

METERS_TO_PX = 70.0


@dataclass
class DragState:
    kind: Literal["pan", "wall-point", "object-move", "object-resize", "cable-point"]
    start_room: Point | None = None
    point_index: int | None = None
    object_id: str | None = None
    cable_id: str | None = None
    last_screen: QPoint | None = None


@dataclass
class CableDraft:
    cable_type: Literal["network", "power230", "power400", "fiber"] = "network"
    label: str = ""
    tag: str = ""
    comment: str = ""
    diameter_mm: float = 10.0
    points: list[RoomPoint] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.points is None:
            self.points = []


class EditorCanvas(QWidget):
    status_changed = Signal(str)
    selection_changed = Signal()
    data_changed = Signal()

    def __init__(self, data: EditorData, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.data = data
        self.mode = "select"
        self.zoom = 1.0
        self.pan = QPointF(24.0, 24.0)
        self.snap_to_grid = True
        self.insert_wall_point_mode = False
        self.drag_state: DragState | None = None

        self.selected_object_id: str | None = None
        self.selected_cable_id: str | None = None
        self.selected_cable_point_index: int | None = None
        self.selected_cable_segment_index: int | None = None
        self.selected_wall_point_index: int | None = None
        self.selected_divider_wall_index: int | None = None

        self.divider_wall_draft_points: list[Point] = []
        self.cable_draft = CableDraft()

    @property
    def active_room(self) -> RoomModel | None:
        for room in self.data.rooms:
            if room.id == self.data.active_room_id:
                return room
        return None

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        if mode != "add-divider-wall":
            self.divider_wall_draft_points = []
        if mode != "add-cable":
            self.cable_draft.points = []
        if mode != "select":
            self.selected_divider_wall_index = None
        self.status_changed.emit(f"Mode: {mode}")
        self.update()

    def set_snap_to_grid(self, enabled: bool) -> None:
        self.snap_to_grid = enabled
        self.update()

    def set_insert_wall_point_mode(self, enabled: bool) -> None:
        self.insert_wall_point_mode = enabled

    def set_cable_draft_meta(
        self,
        cable_type: Literal["network", "power230", "power400", "fiber"],
        label: str,
        tag: str,
        comment: str,
        diameter_mm: float,
    ) -> None:
        self.cable_draft.cable_type = cable_type
        self.cable_draft.label = label
        self.cable_draft.tag = tag
        self.cable_draft.comment = comment
        self.cable_draft.diameter_mm = diameter_mm

    def clear_selection(self) -> None:
        self.selected_object_id = None
        self.selected_cable_id = None
        self.selected_cable_point_index = None
        self.selected_cable_segment_index = None
        self.selected_wall_point_index = None
        self.selected_divider_wall_index = None
        self.selection_changed.emit()
        self.update()

    def _scale(self) -> float:
        return METERS_TO_PX * self.zoom

    def room_to_screen(self, point: Point) -> QPointF:
        scale = self._scale()
        return QPointF(point.x * scale + self.pan.x(), point.y * scale + self.pan.y())

    def screen_to_room(self, point: QPointF, apply_snap: bool = True) -> Point | None:
        room = self.active_room
        if room is None:
            return None
        scale = self._scale()
        x = (point.x() - self.pan.x()) / scale
        y = (point.y() - self.pan.y()) / scale
        x = clamp(x, 0.0, room.width_meters)
        y = clamp(y, 0.0, room.height_meters)
        if apply_snap and self.snap_to_grid and room.grid_size_meters > 0:
            grid = room.grid_size_meters
            x = round(x / grid) * grid
            y = round(y / grid) * grid
        return Point(round_coord(x), round_coord(y))

    def _objects_for_active_room(self) -> list[ObjectModel]:
        room = self.active_room
        if room is None:
            return []
        return [obj for obj in self.data.objects if obj.room_id == room.id]

    def _cables_for_active_room(self) -> list[CableModel]:
        room = self.active_room
        if room is None:
            return []
        return [cable for cable in self.data.cables if any(point.room_id == room.id for point in cable.points)]

    def _object_hit(self, room_pos: Point) -> str | None:
        for obj in reversed(self._objects_for_active_room()):
            left = obj.x
            top = obj.y
            right = obj.x + obj.width
            bottom = obj.y + obj.height
            if left <= room_pos.x <= right and top <= room_pos.y <= bottom:
                return obj.id
        return None

    def _object_resize_handle_hit(self, room_pos: Point) -> str | None:
        tolerance = 0.2
        for obj in reversed(self._objects_for_active_room()):
            rx = obj.x + obj.width
            ry = obj.y + obj.height
            if abs(room_pos.x - rx) <= tolerance and abs(room_pos.y - ry) <= tolerance:
                return obj.id
        return None

    def _wall_point_hit(self, room: RoomModel, room_pos: Point) -> int | None:
        tolerance = 0.2
        for idx, point in enumerate(room.wall_points):
            if abs(point.x - room_pos.x) <= tolerance and abs(point.y - room_pos.y) <= tolerance:
                return idx
        return None

    def _nearest_wall_edge(self, room: RoomModel, room_pos: Point) -> int | None:
        if len(room.wall_points) < 2:
            return None
        best_index = None
        best_distance = 99999.0
        for idx, start in enumerate(room.wall_points):
            end = room.wall_points[(idx + 1) % len(room.wall_points)]
            dist = point_to_segment_distance(room_pos, start, end)
            if dist < best_distance:
                best_distance = dist
                best_index = idx
        if best_distance <= 0.3:
            return best_index
        return None

    def _cable_point_hit(self, room_pos: Point) -> tuple[str, int] | None:
        tolerance = 0.2
        room = self.active_room
        if room is None:
            return None
        for cable in reversed(self._cables_for_active_room()):
            for idx, point in enumerate(cable.points):
                if point.room_id != room.id:
                    continue
                if abs(point.x - room_pos.x) <= tolerance and abs(point.y - room_pos.y) <= tolerance:
                    return cable.id, idx
        return None

    def _cable_segment_hit(self, room_pos: Point) -> tuple[str, int] | None:
        room = self.active_room
        if room is None:
            return None
        best: tuple[str, int] | None = None
        best_distance = 99999.0
        for cable in reversed(self._cables_for_active_room()):
            for idx in range(1, len(cable.points)):
                a = cable.points[idx - 1]
                b = cable.points[idx]
                if a.room_id != room.id or b.room_id != room.id:
                    continue
                dist = point_to_segment_distance(room_pos, a, b)
                if dist < best_distance:
                    best_distance = dist
                    best = (cable.id, idx)
        if best_distance <= 0.25:
            return best
        return None

    def _divider_wall_hit(self, room: RoomModel, room_pos: Point) -> int | None:
        tolerance = 0.2
        for idx, divider in enumerate(room.divider_walls):
            if point_to_segment_distance(room_pos, divider.from_point, divider.to_point) <= tolerance:
                return idx
        return None

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f8f8f8"))

        room = self.active_room
        if room is None:
            painter.end()
            return

        top_left = self.room_to_screen(Point(0, 0))
        bottom_right = self.room_to_screen(Point(room.width_meters, room.height_meters))
        room_rect_x = top_left.x()
        room_rect_y = top_left.y()
        room_rect_w = bottom_right.x() - top_left.x()
        room_rect_h = bottom_right.y() - top_left.y()

        painter.fillRect(room_rect_x, room_rect_y, room_rect_w, room_rect_h, QColor(room.background))

        if room.grid_size_meters > 0:
            painter.setPen(QPen(QColor("#e3e3e3"), 1))
            x = 0.0
            while x <= room.width_meters + 1e-6:
                a = self.room_to_screen(Point(x, 0))
                b = self.room_to_screen(Point(x, room.height_meters))
                painter.drawLine(a, b)
                x += room.grid_size_meters
            y = 0.0
            while y <= room.height_meters + 1e-6:
                a = self.room_to_screen(Point(0, y))
                b = self.room_to_screen(Point(room.width_meters, y))
                painter.drawLine(a, b)
                y += room.grid_size_meters

        wall_pen = QPen(QColor("#222222"), 2)
        painter.setPen(wall_pen)
        wall_points = [self.room_to_screen(point) for point in room.wall_points]
        for idx, start in enumerate(wall_points):
            end = wall_points[(idx + 1) % len(wall_points)]
            painter.drawLine(start, end)

        for idx, point in enumerate(room.wall_points):
            screen_point = self.room_to_screen(point)
            color = QColor("#cc1f1f") if self.selected_wall_point_index == idx else QColor("#111111")
            painter.setBrush(color)
            painter.setPen(QPen(Qt.GlobalColor.black, 1))
            painter.drawEllipse(screen_point, 4, 4)

        painter.setPen(QPen(QColor("#4f46e5"), 2))
        for idx, divider in enumerate(room.divider_walls):
            pen_color = QColor("#312e81") if idx == self.selected_divider_wall_index else QColor("#4f46e5")
            painter.setPen(QPen(pen_color, 3 if idx == self.selected_divider_wall_index else 2))
            painter.drawLine(self.room_to_screen(divider.from_point), self.room_to_screen(divider.to_point))

        if self.divider_wall_draft_points:
            painter.setPen(QPen(QColor("#6366f1"), 1, Qt.PenStyle.DashLine))
            for idx in range(1, len(self.divider_wall_draft_points)):
                painter.drawLine(
                    self.room_to_screen(self.divider_wall_draft_points[idx - 1]),
                    self.room_to_screen(self.divider_wall_draft_points[idx]),
                )
            painter.setBrush(QColor("#111111"))
            for point in self.divider_wall_draft_points:
                painter.drawEllipse(self.room_to_screen(point), 3, 3)

        for obj in self._objects_for_active_room():
            top_left = self.room_to_screen(Point(obj.x, obj.y))
            size_w = obj.width * self._scale()
            size_h = obj.height * self._scale()
            selected = obj.id == self.selected_object_id
            fill = QColor("#a7d3f2" if selected else "#d3e8f8")
            painter.setBrush(fill)
            painter.setPen(QPen(QColor("#204b6b"), 2 if selected else 1))
            if obj.shape == "circle":
                painter.drawEllipse(top_left.x(), top_left.y(), size_w, size_h)
            else:
                painter.drawRect(top_left.x(), top_left.y(), size_w, size_h)
            if obj.label:
                painter.setPen(QPen(QColor("#111111"), 1))
                painter.drawText(
                    QPointF(top_left.x() + 6, top_left.y() + 16),
                    obj.label,
                )

            if selected:
                handle = self.room_to_screen(Point(obj.x + obj.width, obj.y + obj.height))
                painter.setBrush(QColor("#0f172a"))
                painter.drawRect(handle.x() - 4, handle.y() - 4, 8, 8)

        for cable in self._cables_for_active_room():
            points = [point for point in cable.points if point.room_id == room.id]
            if len(points) < 2:
                continue
            pen = QPen(QColor(cable.color), 3 if cable.id == self.selected_cable_id else 2)
            painter.setPen(pen)
            for idx in range(1, len(points)):
                painter.drawLine(self.room_to_screen(points[idx - 1]), self.room_to_screen(points[idx]))
            painter.setBrush(QColor(cable.color))
            for idx, point in enumerate(points):
                radius = 5 if (cable.id == self.selected_cable_id and self.selected_cable_point_index == idx) else 3
                painter.drawEllipse(self.room_to_screen(point), radius, radius)

        if len(self.cable_draft.points) > 0:
            painter.setPen(QPen(QColor(CABLE_TYPE_COLORS[self.cable_draft.cable_type]), 2, Qt.PenStyle.DashLine))
            for idx in range(1, len(self.cable_draft.points)):
                painter.drawLine(
                    self.room_to_screen(self.cable_draft.points[idx - 1]),
                    self.room_to_screen(self.cable_draft.points[idx]),
                )
            painter.setBrush(QColor("#111111"))
            for point in self.cable_draft.points:
                painter.drawEllipse(self.room_to_screen(point), 3, 3)

        painter.end()

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        old_zoom = self.zoom
        self.zoom = clamp(self.zoom * (1.1 if delta > 0 else 0.9), 0.3, 3.5)
        if abs(old_zoom - self.zoom) > 1e-9:
            self.status_changed.emit(f"Zoom: {round(self.zoom, 2)}x")
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        room = self.active_room
        if room is None:
            return

        raw_room_pos = self.screen_to_room(event.position(), apply_snap=False)
        room_pos = self.screen_to_room(event.position(), apply_snap=True)
        if raw_room_pos is None or room_pos is None:
            return

        if event.button() == Qt.MouseButton.MiddleButton:
            self.drag_state = DragState(kind="pan", last_screen=event.pos())
            return

        if self.mode.startswith("add-object-") and event.button() == Qt.MouseButton.LeftButton:
            shape = self.mode.removeprefix("add-object-")
            new_object = create_object(shape, room.id, room_pos.x, room_pos.y)
            self.data.objects.append(new_object)
            self.selected_object_id = new_object.id
            self.selected_cable_id = None
            self.selected_cable_point_index = None
            self.selected_cable_segment_index = None
            self.selected_wall_point_index = None
            self.set_mode("select")
            self.selection_changed.emit()
            self.data_changed.emit()
            self.status_changed.emit(f"Object added: {shape}")
            self.update()
            return

        if self.mode == "add-divider-wall":
            if event.button() == Qt.MouseButton.LeftButton:
                if not self.divider_wall_draft_points:
                    self.divider_wall_draft_points = [room_pos]
                else:
                    last_point = self.divider_wall_draft_points[-1]
                    if abs(last_point.x - room_pos.x) <= 1e-6 and abs(last_point.y - room_pos.y) <= 1e-6:
                        self.status_changed.emit("Divider wall point already set.")
                        return
                    self.divider_wall_draft_points.append(room_pos)
                self.status_changed.emit(
                    "Divider wall point added. Continue clicking corners or right-click to finish."
                )
                self.update()
                return
            if event.button() == Qt.MouseButton.RightButton:
                if self.finish_divider_wall_draft():
                    self.set_mode("select")
                return

        if self.mode == "add-cable":
            if event.button() == Qt.MouseButton.LeftButton:
                self.cable_draft.points.append(RoomPoint(room_pos.x, room_pos.y, room.id))
                self.status_changed.emit(f"Cable point added ({len(self.cable_draft.points)}).")
                self.update()
                return
            if event.button() == Qt.MouseButton.RightButton:
                if self.finish_cable_draft():
                    self.set_mode("select")
                return

        if self.mode == "edit-walls" and event.button() == Qt.MouseButton.LeftButton:
            wall_point_idx = self._wall_point_hit(room, raw_room_pos)
            if wall_point_idx is not None:
                self.selected_wall_point_index = wall_point_idx
                self.selected_object_id = None
                self.selected_cable_id = None
                self.selected_cable_point_index = None
                self.selected_cable_segment_index = None
                self.drag_state = DragState(
                    kind="wall-point",
                    start_room=raw_room_pos,
                    point_index=wall_point_idx,
                )
                self.selection_changed.emit()
                self.update()
                return

            if self.insert_wall_point_mode:
                edge_idx = self._nearest_wall_edge(room, raw_room_pos)
                if edge_idx is not None:
                    room.wall_points.insert(edge_idx + 1, Point(room_pos.x, room_pos.y))
                    self.selected_wall_point_index = edge_idx + 1
                    self.selection_changed.emit()
                    self.data_changed.emit()
                    self.status_changed.emit("Wall point inserted.")
                    self.update()
                    return

        if event.button() == Qt.MouseButton.LeftButton:
            resize_hit = self._object_resize_handle_hit(raw_room_pos)
            if resize_hit:
                self.selected_object_id = resize_hit
                self.selected_cable_id = None
                self.selected_cable_point_index = None
                self.selected_wall_point_index = None
                self.selected_cable_segment_index = None
                self.drag_state = DragState(kind="object-resize", object_id=resize_hit, start_room=raw_room_pos)
                self.selection_changed.emit()
                self.update()
                return

            object_hit = self._object_hit(raw_room_pos)
            if object_hit:
                self.selected_object_id = object_hit
                self.selected_cable_id = None
                self.selected_cable_point_index = None
                self.selected_wall_point_index = None
                self.selected_cable_segment_index = None
                self.drag_state = DragState(kind="object-move", object_id=object_hit, start_room=raw_room_pos)
                self.selection_changed.emit()
                self.update()
                return

            cable_point = self._cable_point_hit(raw_room_pos)
            if cable_point:
                cable_id, point_idx = cable_point
                self.selected_object_id = None
                self.selected_wall_point_index = None
                self.selected_cable_id = cable_id
                self.selected_cable_point_index = point_idx
                self.selected_cable_segment_index = None
                self.drag_state = DragState(
                    kind="cable-point",
                    cable_id=cable_id,
                    point_index=point_idx,
                    start_room=raw_room_pos,
                )
                self.selection_changed.emit()
                self.update()
                return

            cable_segment = self._cable_segment_hit(raw_room_pos)
            if cable_segment:
                cable_id, segment_index = cable_segment
                self.selected_object_id = None
                self.selected_wall_point_index = None
                self.selected_cable_id = cable_id
                self.selected_cable_point_index = None
                self.selected_cable_segment_index = segment_index
                self.selection_changed.emit()
                self.update()
                return

            divider_hit = self._divider_wall_hit(room, raw_room_pos)
            if divider_hit is not None:
                self.selected_divider_wall_index = divider_hit
                self.selected_object_id = None
                self.selected_cable_id = None
                self.selected_cable_point_index = None
                self.selected_cable_segment_index = None
                self.selected_wall_point_index = None
                self.selection_changed.emit()
                self.update()
                return

            self.clear_selection()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        room = self.active_room
        if room is None:
            return
        if self.drag_state is None:
            return

        if self.drag_state.kind == "pan" and self.drag_state.last_screen is not None:
            delta = event.pos() - self.drag_state.last_screen
            self.pan = QPointF(self.pan.x() + delta.x(), self.pan.y() + delta.y())
            self.drag_state.last_screen = event.pos()
            self.update()
            return

        room_pos = self.screen_to_room(event.position())
        if room_pos is None:
            return

        if self.drag_state.kind == "wall-point":
            idx = self.drag_state.point_index
            if idx is not None and 0 <= idx < len(room.wall_points):
                room.wall_points[idx].x = room_pos.x
                room.wall_points[idx].y = room_pos.y
                self.data_changed.emit()
                self.update()
            return

        if self.drag_state.kind == "object-move" and self.drag_state.object_id:
            obj = next((item for item in self.data.objects if item.id == self.drag_state.object_id), None)
            if obj:
                obj.x = round_coord(clamp(room_pos.x, 0.0, room.width_meters - obj.width))
                obj.y = round_coord(clamp(room_pos.y, 0.0, room.height_meters - obj.height))
                self.data_changed.emit()
                self.update()
            return

        if self.drag_state.kind == "object-resize" and self.drag_state.object_id:
            obj = next((item for item in self.data.objects if item.id == self.drag_state.object_id), None)
            if obj:
                obj.width = round_coord(max(0.2, room_pos.x - obj.x))
                obj.height = round_coord(max(0.2, room_pos.y - obj.y))
                self.data_changed.emit()
                self.update()
            return

        if self.drag_state.kind == "cable-point" and self.drag_state.cable_id is not None:
            cable = next((item for item in self.data.cables if item.id == self.drag_state.cable_id), None)
            point_index = self.drag_state.point_index
            if cable and point_index is not None and 0 <= point_index < len(cable.points):
                current = cable.points[point_index]
                current.x = room_pos.x
                current.y = room_pos.y
                current.room_id = room.id
                self.data_changed.emit()
                self.update()
            return

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.drag_state = None

    def finish_divider_wall_draft(self) -> bool:
        room = self.active_room
        if room is None:
            return False
        if len(self.divider_wall_draft_points) < 2:
            self.status_changed.emit("Divider wall requires at least two points.")
            return False
        for idx in range(1, len(self.divider_wall_draft_points)):
            room.divider_walls.append(
                DividerWallSegment(self.divider_wall_draft_points[idx - 1], self.divider_wall_draft_points[idx])
            )
        self.divider_wall_draft_points = []
        self.selected_divider_wall_index = None
        self.data_changed.emit()
        self.status_changed.emit("Divider wall placed.")
        self.update()
        return True

    def finish_cable_draft(self) -> bool:
        room = self.active_room
        if room is None:
            return False
        if len(self.cable_draft.points) < 2:
            self.status_changed.emit("Cable requires at least two points.")
            return False
        cable = create_cable(
            self.cable_draft.cable_type,
            self.cable_draft.label,
            self.cable_draft.tag,
            self.cable_draft.comment,
            self.cable_draft.diameter_mm,
            list(self.cable_draft.points),
        )
        self.data.cables.append(cable)
        self.selected_cable_id = cable.id
        self.selected_cable_point_index = None
        self.selected_cable_segment_index = None
        self.selected_object_id = None
        self.selected_wall_point_index = None
        self.cable_draft.points = []
        self.selection_changed.emit()
        self.data_changed.emit()
        self.status_changed.emit("Cable created.")
        self.update()
        return True

    def cancel_cable_draft(self) -> None:
        self.cable_draft.points = []
        self.status_changed.emit("Cable draft cancelled.")
        self.update()

    def insert_point_on_selected_cable_segment(self) -> bool:
        if self.selected_cable_id is None or self.selected_cable_segment_index is None:
            self.status_changed.emit("Select a cable segment first.")
            return False
        cable = next((item for item in self.data.cables if item.id == self.selected_cable_id), None)
        if cable is None:
            return False
        idx = self.selected_cable_segment_index
        if idx <= 0 or idx >= len(cable.points):
            return False
        a = cable.points[idx - 1]
        b = cable.points[idx]
        midpoint = RoomPoint(
            x=round_coord((a.x + b.x) / 2.0),
            y=round_coord((a.y + b.y) / 2.0),
            room_id=a.room_id,
        )
        cable.points.insert(idx, midpoint)
        cable.bend_radius_meters.insert(max(0, idx - 1), 0.0)
        self.selected_cable_point_index = idx
        self.selected_cable_segment_index = None
        self.data_changed.emit()
        self.selection_changed.emit()
        self.status_changed.emit("Cable bend point inserted.")
        self.update()
        return True
