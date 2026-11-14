export type Point = {
  x: number;
  y: number;
};

export type RoomPoint = Point & {
  roomId: string;
};

export type CableType = "network" | "power230" | "power400" | "fiber";

export type DividerWallSegment = {
  from: Point;
  to: Point;
};

export type RoomModel = {
  id: string;
  name: string;
  widthMeters: number;
  heightMeters: number;
  wallPoints: Point[];
  dividerWalls: DividerWallSegment[];
  gridSizeMeters: number;
  background: string;
};

export type ShapeType = "square" | "rectangle" | "circle";

export type ObjectModel = {
  id: string;
  roomId: string;
  shape: ShapeType;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  name: string;
  comment: string;
};

export type CableModel = {
  id: string;
  label: string;
  tag: string;
  comment: string;
  type: CableType;
  diameterMm: number;
  color: string;
  points: RoomPoint[];
  bendRadiusMeters: number[];
  lengthMode: "dynamic" | "fixed";
  fixedLengthMeters: number | null;
};

export type EditorData = {
  version: 1;
  rooms: RoomModel[];
  objects: ObjectModel[];
  cables: CableModel[];
  activeRoomId: string | null;
};

export type Selection =
  | { kind: "none" }
  | { kind: "wall-point"; roomId: string; pointIndex: number }
  | { kind: "wall-edge"; roomId: string; edgeIndex: number }
  | { kind: "object"; objectId: string }
  | { kind: "cable"; cableId: string; pointIndex?: number }
  | { kind: "cable-segment"; cableId: string; segmentIndex: number };
