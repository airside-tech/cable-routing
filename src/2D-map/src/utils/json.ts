import type { EditorData, RoomModel } from "../types";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

const normalizeRoom = (room: unknown): RoomModel | null => {
  if (!isRecord(room)) return null;
  if (!Array.isArray(room.wallPoints)) return null;

  const normalized = {
    ...room,
    wallPoints: room.wallPoints,
    dividerWalls: Array.isArray(room.dividerWalls) ? room.dividerWalls : [],
    gridSizeMeters: typeof room.gridSizeMeters === "number" ? room.gridSizeMeters : 1,
    background: typeof room.background === "string" ? room.background : "#f4f5f7",
  } as RoomModel;

  return normalized;
};

export const validateProjectData = (value: unknown): value is EditorData => {
  if (!isRecord(value)) return false;
  if (value.version !== 1) return false;
  if (!Array.isArray(value.rooms) || !Array.isArray(value.objects) || !Array.isArray(value.cables)) {
    return false;
  }
  if (value.activeRoomId !== null && typeof value.activeRoomId !== "string") {
    return false;
  }
  return value.rooms.every((room) => normalizeRoom(room) !== null);
};

export const exportProjectJson = (data: EditorData): string => JSON.stringify(data, null, 2);

export const importProjectJson = (content: string): EditorData => {
  const parsed = JSON.parse(content) as unknown;
  if (!isRecord(parsed) || !Array.isArray(parsed.rooms)) {
    throw new Error("Invalid 2D map JSON format.");
  }

  const normalizedRooms = parsed.rooms.map((room) => normalizeRoom(room)).filter((room): room is RoomModel => room !== null);
  const normalized: EditorData = {
    version: 1,
    rooms: normalizedRooms,
    objects: Array.isArray(parsed.objects) ? parsed.objects : [],
    cables: Array.isArray(parsed.cables) ? parsed.cables : [],
    activeRoomId: typeof parsed.activeRoomId === "string" || parsed.activeRoomId === null ? parsed.activeRoomId : null,
  };

  if (!validateProjectData(normalized)) {
    throw new Error("Invalid 2D map JSON format.");
  }

  return normalized;
};
