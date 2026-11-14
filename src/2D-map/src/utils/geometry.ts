import type { CableModel, Point, RoomModel, RoomPoint } from "../types";

const hypot = (dx: number, dy: number): number => Math.sqrt(dx * dx + dy * dy);

export const distance = (a: Point, b: Point): number => hypot(a.x - b.x, a.y - b.y);

export const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

export const snap = (value: number, grid: number): number => {
  if (grid <= 0) {
    return value;
  }
  return Math.round(value / grid) * grid;
};

export const snapPoint = (p: Point, grid: number): Point => ({
  x: snap(p.x, grid),
  y: snap(p.y, grid),
});

export const getCableColor = (type: CableModel["type"]): string => {
  if (type === "network") return "#777777";
  if (type === "power230" || type === "power400") return "#111111";
  return "#b8860b";
};

export const segmentLengthMeters = (a: RoomPoint, b: RoomPoint): number => {
  if (a.roomId !== b.roomId) {
    return 0;
  }
  return distance(a, b);
};

export const cableLengthMeters = (cable: CableModel): number => {
  if (cable.lengthMode === "fixed" && cable.fixedLengthMeters !== null) {
    return cable.fixedLengthMeters;
  }
  let total = 0;
  for (let i = 1; i < cable.points.length; i += 1) {
    total += segmentLengthMeters(cable.points[i - 1], cable.points[i]);
  }
  return total;
};

export const nearestEdgePoint = (
  polygon: Point[],
  target: Point,
): { edgeIndex: number; point: Point; distanceMeters: number } | null => {
  if (polygon.length < 2) {
    return null;
  }
  let best: { edgeIndex: number; point: Point; distanceMeters: number } | null = null;
  for (let i = 0; i < polygon.length; i += 1) {
    const a = polygon[i];
    const b = polygon[(i + 1) % polygon.length];
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const apx = target.x - a.x;
    const apy = target.y - a.y;
    const denom = abx * abx + aby * aby;
    const t = denom > 0 ? clamp((apx * abx + apy * aby) / denom, 0, 1) : 0;
    const p = { x: a.x + abx * t, y: a.y + aby * t };
    const d = distance(p, target);
    if (!best || d < best.distanceMeters) {
      best = { edgeIndex: i, point: p, distanceMeters: d };
    }
  }
  return best;
};

export const roomBounds = (room: RoomModel): { minX: number; minY: number; maxX: number; maxY: number } => ({
  minX: 0,
  minY: 0,
  maxX: room.widthMeters,
  maxY: room.heightMeters,
});
