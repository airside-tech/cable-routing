import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { TOOL_REGISTRY } from "./tooling/toolRegistry";
import type { CableModel, CableType, EditorData, ObjectModel, Point, RoomModel, RoomPoint, Selection } from "./types";
import { clamp, cableLengthMeters, distance, getCableColor, nearestEdgePoint, roomBounds, segmentLengthMeters, snapPoint } from "./utils/geometry";
import { exportProjectJson, importProjectJson } from "./utils/json";
import { makeId } from "./utils/ids";
import { clearDraft, loadDraft, saveDraft } from "./utils/storage";

const METERS_TO_PX = 70;
const COORD_PRECISION = 2;
const FIXED_LENGTH_TOLERANCE_METERS = 0.01;
const STAPLED_MATCH_TOLERANCE_METERS = 0.1;
const MAX_STAPLE_INSERTIONS = 3;

type ToolGroup = "room" | "object";
type DragMode = "wall-point" | "wall-edge" | "object-move" | "object-resize" | "cable-point";

type DragState = {
  mode: DragMode;
  roomPosStart: Point;
  targetId: string;
  index?: number;
  initialPoint?: Point;
  secondaryPoint?: Point;
  initialObject?: Pick<ObjectModel, "x" | "y" | "width" | "height">;
  initialCablePoints?: RoomPoint[];
};

type CableDraft = {
  type: CableType;
  label: string;
  tag: string;
  comment: string;
  diameterMm: number;
  points: RoomPoint[];
};

type FixedRouteReconcileStatus =
  | "exact"
  | "clamped"
  | "stapled"
  | "best-effort-short"
  | "best-effort-long";

type FixedRouteReconcileResult = {
  points: RoomPoint[];
  status: FixedRouteReconcileStatus;
  lengthGapMeters: number;
  insertedPoints: number;
};

const roundTo = (value: number, precision: number): number => {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
};

const roundCoord = (value: number): number => roundTo(value, COORD_PRECISION);
const roundPoint = (point: Point): Point => ({ x: roundCoord(point.x), y: roundCoord(point.y) });
const clampPointToBounds = (point: Point, width: number, height: number): Point =>
  roundPoint({
    x: clamp(point.x, 0, width),
    y: clamp(point.y, 0, height),
  });
const calculatePolylineLength = (points: RoomPoint[]): number => {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += segmentLengthMeters(points[i - 1], points[i]);
  }
  return roundCoord(total);
};

const calculatePolylineLengthForPoints = (points: Point[]): number => {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += distance(points[i - 1], points[i]);
  }
  return roundCoord(total);
};

const clampMoveWithinFixedLength = (
  baselinePoints: RoomPoint[],
  movedIndex: number,
  desiredPoints: RoomPoint[],
  lockedLength: number,
): RoomPoint[] | null => {
  let workingPoints = [...desiredPoints];
  if (calculatePolylineLength(workingPoints) <= lockedLength + FIXED_LENGTH_TOLERANCE_METERS) {
    return workingPoints;
  }
  const originalPoint = baselinePoints[movedIndex];
  const desiredPoint = desiredPoints[movedIndex];
  if (!originalPoint || !desiredPoint) {
    return null;
  }

  let low = 0;
  let high = 1;
  for (let i = 0; i < 24; i += 1) {
    const mid = (low + high) / 2;
    const candidatePoint = roundPoint({
      x: originalPoint.x + (desiredPoint.x - originalPoint.x) * mid,
      y: originalPoint.y + (desiredPoint.y - originalPoint.y) * mid,
    });
    const candidate = [...workingPoints];
    candidate[movedIndex] = { ...candidate[movedIndex], x: candidatePoint.x, y: candidatePoint.y };
    const candidateLength = calculatePolylineLength(candidate);
    if (candidateLength > lockedLength) {
      high = mid;
    } else {
      low = mid;
      workingPoints = candidate;
    }
  }

  if (calculatePolylineLength(workingPoints) > lockedLength + FIXED_LENGTH_TOLERANCE_METERS) {
    return null;
  }
  return workingPoints;
};

const createRoom = (name: string, widthMeters: number, heightMeters: number): RoomModel => ({
  id: makeId("room"),
  name,
  widthMeters: roundCoord(widthMeters),
  heightMeters: roundCoord(heightMeters),
  wallPoints: [
    { x: 0, y: 0 },
    { x: widthMeters, y: 0 },
    { x: widthMeters, y: heightMeters },
    { x: 0, y: heightMeters },
  ],
  dividerWalls: [],
  gridSizeMeters: 1,
  background: "#f4f5f7",
});

const createInitialData = (): EditorData => {
  const firstRoom = createRoom("Room A", 8, 6);
  return {
    version: 1,
    rooms: [firstRoom],
    objects: [],
    cables: [],
    activeRoomId: firstRoom.id,
  };
};

const toPointsAttribute = (points: Point[]): string => points.map((p) => `${p.x},${p.y}`).join(" ");

const findRoom = (data: EditorData, id: string | null): RoomModel | null =>
  data.rooms.find((r) => r.id === id) ?? null;

const App = () => {
  const [data, setData] = useState<EditorData>(() => loadDraft() ?? createInitialData());
  const [selection, setSelection] = useState<Selection>({ kind: "none" });
  const [activeGroup, setActiveGroup] = useState<ToolGroup>("room");
  const [insertWallPointMode, setInsertWallPointMode] = useState(false);
  const [snapToGrid, setSnapToGrid] = useState(true);
  const [status, setStatus] = useState("Ready");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState<Point>({ x: 20, y: 20 });
  const [newRoomName, setNewRoomName] = useState("Room B");
  const [newRoomWidth, setNewRoomWidth] = useState(6);
  const [newRoomHeight, setNewRoomHeight] = useState(5);
  const [cableDraft, setCableDraft] = useState<CableDraft | null>(null);
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [showWallSegmentLengths, setShowWallSegmentLengths] = useState(false);
  const [dividerWallDraft, setDividerWallDraft] = useState<Point | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const activeRoom = useMemo(() => findRoom(data, data.activeRoomId), [data, data.activeRoomId]);
  const roomObjects = useMemo(
    () => data.objects.filter((obj) => obj.roomId === activeRoom?.id),
    [data.objects, activeRoom?.id],
  );

  useEffect(() => {
    saveDraft(data);
  }, [data]);

  useEffect(() => {
    if (!activeRoom) {
      setSelection({ kind: "none" });
      return;
    }
    setSelection((prev) => {
      if (prev.kind === "none") return prev;
      if (prev.kind === "wall-point" || prev.kind === "wall-edge") {
        return prev.roomId === activeRoom.id ? prev : { kind: "none" };
      }
      if (prev.kind === "object") {
        return data.objects.some((obj) => obj.id === prev.objectId && obj.roomId === activeRoom.id) ? prev : { kind: "none" };
      }
      if (prev.kind === "cable") {
        return data.cables.some((cable) => cable.id === prev.cableId && cable.points.some((point) => point.roomId === activeRoom.id))
          ? prev
          : { kind: "none" };
      }
      if (prev.kind === "cable-segment") {
        return data.cables.some(
          (cable) => cable.id === prev.cableId && prev.segmentIndex >= 1 && prev.segmentIndex < cable.points.length,
        )
          ? prev
          : { kind: "none" };
      }
      return { kind: "none" };
    });
  }, [activeRoom?.id, data.objects, data.cables, activeRoom]);

  const activeRoomCables = useMemo(() => {
    if (!activeRoom) {
      return [] as CableModel[];
    }
    return data.cables.filter((cable) => cable.points.some((p) => p.roomId === activeRoom.id));
  }, [activeRoom, data.cables]);

  const toRoomCoordsFromClient = (clientX: number, clientY: number): Point | null => {
    if (!svgRef.current || !activeRoom) {
      return null;
    }
    const rect = svgRef.current.getBoundingClientRect();
    const pxScale = zoom * METERS_TO_PX;
    const x = (clientX - rect.left - pan.x) / pxScale;
    const y = (clientY - rect.top - pan.y) / pxScale;
    const { minX, maxX, minY, maxY } = roomBounds(activeRoom);
    return roundPoint({
      x: clamp(x, minX, maxX),
      y: clamp(y, minY, maxY),
    });
  };

  const toRoomCoords = (event: { clientX: number; clientY: number }): Point | null =>
    toRoomCoordsFromClient(event.clientX, event.clientY);

  const updateRoom = (roomId: string, updater: (room: RoomModel) => RoomModel) => {
    setData((prev) => ({
      ...prev,
      rooms: prev.rooms.map((room) => (room.id === roomId ? updater(room) : room)),
    }));
  };

  const updateSelectedRoom = (updater: (room: RoomModel) => RoomModel) => {
    if (!activeRoom) return;
    setData((prev) => {
      const currentRoom = prev.rooms.find((room) => room.id === activeRoom.id);
      if (!currentRoom) {
        return prev;
      }
      const nextRoom = updater(currentRoom);
      const nextWidth = roundCoord(Math.max(1, nextRoom.widthMeters));
      const nextHeight = roundCoord(Math.max(1, nextRoom.heightMeters));
      const normalizedRoom: RoomModel = {
        ...nextRoom,
        widthMeters: nextWidth,
        heightMeters: nextHeight,
        wallPoints: nextRoom.wallPoints.map((point) => clampPointToBounds(point, nextWidth, nextHeight)),
        dividerWalls: nextRoom.dividerWalls.map((segment) => ({
          from: clampPointToBounds(segment.from, nextWidth, nextHeight),
          to: clampPointToBounds(segment.to, nextWidth, nextHeight),
        })),
      };

      const nextObjects = prev.objects.map((obj) => {
        if (obj.roomId !== normalizedRoom.id) {
          return obj;
        }
        const width = roundCoord(clamp(obj.width, 0.2, nextWidth));
        const height = roundCoord(clamp(obj.height, 0.2, nextHeight));
        return {
          ...obj,
          width,
          height,
          x: roundCoord(clamp(obj.x, 0, nextWidth - width)),
          y: roundCoord(clamp(obj.y, 0, nextHeight - height)),
        };
      });

      const nextCables = prev.cables.map((cable) => ({
        ...cable,
        points: cable.points.map((point) =>
          point.roomId === normalizedRoom.id
            ? {
                ...point,
                ...clampPointToBounds(point, nextWidth, nextHeight),
              }
            : point,
        ),
      }));

      return {
        ...prev,
        rooms: prev.rooms.map((room) => (room.id === normalizedRoom.id ? normalizedRoom : room)),
        objects: nextObjects,
        cables: nextCables,
      };
    });
  };

  const addRoom = () => {
    const width = roundCoord(Math.max(1, Number(newRoomWidth)));
    const height = roundCoord(Math.max(1, Number(newRoomHeight)));
    const room = createRoom(newRoomName.trim() || `Room ${data.rooms.length + 1}`, width, height);
    setData((prev) => ({
      ...prev,
      rooms: [...prev.rooms, room],
      activeRoomId: room.id,
    }));
    setSelection({ kind: "none" });
    setStatus(`Created ${room.name}`);
  };

  const addWallSegment = () => {
    if (!activeRoom || activeRoom.wallPoints.length < 2) {
      return;
    }
    let longestEdgeIndex = 0;
    let longestLength = -1;
    for (let i = 0; i < activeRoom.wallPoints.length; i += 1) {
      const from = activeRoom.wallPoints[i];
      const to = activeRoom.wallPoints[(i + 1) % activeRoom.wallPoints.length];
      const edgeLength = distance(from, to);
      if (edgeLength > longestLength) {
        longestLength = edgeLength;
        longestEdgeIndex = i;
      }
    }
    const from = activeRoom.wallPoints[longestEdgeIndex];
    const to = activeRoom.wallPoints[(longestEdgeIndex + 1) % activeRoom.wallPoints.length];
    const midpoint = roundPoint({ x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 });
    updateRoom(activeRoom.id, (room) => {
      const next = [...room.wallPoints];
      next.splice(longestEdgeIndex + 1, 0, midpoint);
      return { ...room, wallPoints: next };
    });
    setSelection({ kind: "wall-point", roomId: activeRoom.id, pointIndex: longestEdgeIndex + 1 });
    setStatus("Added wall segment point on longest wall edge.");
  };

  const reconcileFixedLengthRoute = (
    baselineCable: CableModel,
    movedIndex: number,
    desiredPoints: RoomPoint[],
  ): FixedRouteReconcileResult => {
    const fallbackGap =
      (baselineCable.fixedLengthMeters ?? calculatePolylineLength(baselineCable.points)) - calculatePolylineLength(desiredPoints);
    if (!activeRoom) {
      return {
        points: desiredPoints,
        status: fallbackGap >= 0 ? "best-effort-short" : "best-effort-long",
        lengthGapMeters: roundCoord(fallbackGap),
        insertedPoints: 0,
      };
    }
    const lockedLength = baselineCable.fixedLengthMeters ?? calculatePolylineLength(baselineCable.points);
    let workingPoints = [...desiredPoints];
    let usedClamp = false;
    let insertedPoints = 0;

    if (calculatePolylineLength(workingPoints) > lockedLength + FIXED_LENGTH_TOLERANCE_METERS) {
      const clampedPoints = clampMoveWithinFixedLength(baselineCable.points, movedIndex, desiredPoints, lockedLength);
      if (clampedPoints) {
        workingPoints = clampedPoints;
        usedClamp = true;
      }
    }

    for (let insertion = 0; insertion < MAX_STAPLE_INSERTIONS; insertion += 1) {
      const remaining = lockedLength - calculatePolylineLength(workingPoints);
      if (remaining <= FIXED_LENGTH_TOLERANCE_METERS) {
        return {
          points: workingPoints,
          status: insertedPoints > 0 ? "stapled" : usedClamp ? "clamped" : "exact",
          lengthGapMeters: roundCoord(lockedLength - calculatePolylineLength(workingPoints)),
          insertedPoints,
        };
      }

      const points2d = workingPoints.map((point) => ({ x: point.x, y: point.y }));
      const baseLength = calculatePolylineLengthForPoints(points2d);
      const preferredStartIndex = Math.max(0, movedIndex - 1);
      const preferredEndIndex = Math.min(workingPoints.length - 1, movedIndex + 1);
      const prioritizedSegments: Array<[number, number]> = [];
      for (let i = preferredStartIndex; i < preferredEndIndex; i += 1) {
        if (i >= 0 && i + 1 < workingPoints.length) {
          prioritizedSegments.push([i, i + 1]);
        }
      }
      for (let i = 0; i < workingPoints.length - 1; i += 1) {
        if (i >= preferredStartIndex && i < preferredEndIndex) {
          continue;
        }
        prioritizedSegments.push([i, i + 1]);
      }

      let bestCandidate:
        | {
            startIdx: number;
            endIdx: number;
            a: Point;
            b: Point;
            gap: number;
          }
        | null = null;

      for (const [startIdx, endIdx] of prioritizedSegments) {
        const start = workingPoints[startIdx];
        const end = workingPoints[endIdx];
        if (!start || !end || start.roomId !== activeRoom.id || end.roomId !== activeRoom.id) {
          continue;
        }
        const dx = end.x - start.x;
        const dy = end.y - start.y;
        const segLen = Math.sqrt(dx * dx + dy * dy);
        if (segLen <= 0.0001) {
          continue;
        }
        const ux = -dy / segLen;
        const uy = dx / segLen;
        const baseRise = Math.max(remaining / 2, 0.05);
        const riseFactors = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

        for (const sign of [1, -1]) {
          for (const factor of riseFactors) {
            const rise = baseRise * factor;
            const a = clampPointToBounds(
              { x: start.x + ux * rise * sign, y: start.y + uy * rise * sign },
              activeRoom.widthMeters,
              activeRoom.heightMeters,
            );
            const b = clampPointToBounds(
              { x: end.x + ux * rise * sign, y: end.y + uy * rise * sign },
              activeRoom.widthMeters,
              activeRoom.heightMeters,
            );

            const candidate2d = [...points2d];
            candidate2d.splice(endIdx, 0, a, b);
            const delta = calculatePolylineLengthForPoints(candidate2d) - baseLength;
            if (delta <= 0) {
              continue;
            }
            const gap = Math.abs(remaining - delta);
            if (!bestCandidate || gap < bestCandidate.gap) {
              bestCandidate = { startIdx, endIdx, a, b, gap };
            }
          }
        }
      }

      if (!bestCandidate) {
        break;
      }

      const start = workingPoints[bestCandidate.startIdx];
      const end = workingPoints[bestCandidate.endIdx];
      workingPoints = [...workingPoints];
      workingPoints.splice(
        bestCandidate.endIdx,
        0,
        { ...start, x: bestCandidate.a.x, y: bestCandidate.a.y },
        { ...end, x: bestCandidate.b.x, y: bestCandidate.b.y },
      );
      insertedPoints += 2;

      if (bestCandidate.gap <= STAPLED_MATCH_TOLERANCE_METERS) {
        const finalLength = calculatePolylineLength(workingPoints);
        if (Math.abs(finalLength - lockedLength) <= STAPLED_MATCH_TOLERANCE_METERS) {
          return {
            points: workingPoints,
            status: "stapled",
            lengthGapMeters: roundCoord(lockedLength - finalLength),
            insertedPoints,
          };
        }
      }
    }

    const finalLength = calculatePolylineLength(workingPoints);
    const gap = roundCoord(lockedLength - finalLength);
    if (Math.abs(gap) <= STAPLED_MATCH_TOLERANCE_METERS) {
      return {
        points: workingPoints,
        status: insertedPoints > 0 ? "stapled" : usedClamp ? "clamped" : "exact",
        lengthGapMeters: gap,
        insertedPoints,
      };
    }
    return {
      points: workingPoints,
      status: gap >= 0 ? "best-effort-short" : "best-effort-long",
      lengthGapMeters: gap,
      insertedPoints,
    };
  };

  const fixedLengthStatusMessage = (action: "move" | "bend", result: FixedRouteReconcileResult): string => {
    const actionLabel = action === "move" ? "Move" : "Bend insert";
    if (result.status === "exact") {
      return `${actionLabel} applied with fixed total length preserved.`;
    }
    if (result.status === "clamped") {
      return `${actionLabel} clamped to preserve fixed total length.`;
    }
    if (result.status === "stapled") {
      return `${actionLabel} applied with stapled assist to preserve fixed total length.`;
    }
    if (result.status === "best-effort-short") {
      return `${actionLabel} applied (best effort): route is ${Math.abs(result.lengthGapMeters).toFixed(2)} m shorter than locked fixed total length.`;
    }
    return `${actionLabel} applied (best effort): route is ${Math.abs(result.lengthGapMeters).toFixed(2)} m longer than locked fixed total length.`;
  };

  const handleCanvasClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!activeRoom) return;
    const roomPoint = toRoomCoords(event.nativeEvent);
    if (!roomPoint) return;
    const point = roundPoint(snapToGrid ? snapPoint(roomPoint, activeRoom.gridSizeMeters) : roomPoint);

    if (dividerWallDraft) {
      if (!Number.isFinite(dividerWallDraft.x) || !Number.isFinite(dividerWallDraft.y)) {
        setDividerWallDraft(point);
        setStatus("Divider wall start selected. Click a second point to finish.");
        return;
      }

      const draftStart = dividerWallDraft;
      updateRoom(activeRoom.id, (room) => ({
        ...room,
        dividerWalls: [...room.dividerWalls, { from: draftStart, to: point }],
      }));
      setDividerWallDraft(null);
      setStatus("Added standalone room divider wall.");
      return;
    }

    if (cableDraft) {
      setCableDraft((prev) =>
        prev
          ? {
              ...prev,
              points: [
                ...prev.points,
                {
                  roomId: activeRoom.id,
                  x: point.x,
                  y: point.y,
                },
              ],
            }
          : prev,
      );
      setStatus("Added cable segment point.");
      return;
    }

    if (insertWallPointMode) {
      const nearest = nearestEdgePoint(activeRoom.wallPoints, point);
      if (nearest) {
        updateRoom(activeRoom.id, (room) => {
          const next = [...room.wallPoints];
          next.splice(nearest.edgeIndex + 1, 0, point);
          return { ...room, wallPoints: next };
        });
        setSelection({ kind: "wall-point", roomId: activeRoom.id, pointIndex: nearest.edgeIndex + 1 });
      }
    } else {
      if (selection.kind !== "cable") {
        setSelection({ kind: "none" });
      }
    }
  };

  const addObject = (shape: ObjectModel["shape"]) => {
    if (!activeRoom) return;
    const size = shape === "rectangle" ? { width: 2, height: 1 } : { width: 1.5, height: 1.5 };
    const obj: ObjectModel = {
      id: makeId("obj"),
      roomId: activeRoom.id,
      shape,
      x: roundCoord(activeRoom.widthMeters / 2 - size.width / 2),
      y: roundCoord(activeRoom.heightMeters / 2 - size.height / 2),
      width: roundCoord(size.width),
      height: roundCoord(size.height),
      label: `${shape} label`,
      name: `${shape}-${data.objects.length + 1}`,
      comment: "",
    };
    setData((prev) => ({ ...prev, objects: [...prev.objects, obj] }));
    setSelection({ kind: "object", objectId: obj.id });
    setStatus(`Added ${shape}`);
  };

  const startCableDraft = (type: CableType) => {
    setCableDraft({
      type,
      label: "",
      tag: `CBL-${data.cables.length + 1}`,
      comment: "",
      diameterMm: 8,
      points: [],
    });
    setStatus("Cable placement started. Click in room(s) to add points.");
    setSelection({ kind: "none" });
  };

  const finishCableDraft = () => {
    if (!cableDraft) return;
    if (cableDraft.points.length < 2) {
      setStatus("Cable needs at least 2 points.");
      return;
    }
    const cable: CableModel = {
      id: makeId("cable"),
      label: cableDraft.label,
      tag: cableDraft.tag,
      comment: cableDraft.comment,
      type: cableDraft.type,
      diameterMm: cableDraft.diameterMm,
      color: getCableColor(cableDraft.type),
      points: cableDraft.points,
      bendRadiusMeters: [],
      lengthMode: "dynamic",
      fixedLengthMeters: null,
    };
    setData((prev) => ({ ...prev, cables: [...prev.cables, cable] }));
    setSelection({ kind: "cable", cableId: cable.id });
    setCableDraft(null);
    setStatus("Cable created.");
  };

  const cancelCableDraft = () => {
    setCableDraft(null);
    setStatus("Cable placement canceled.");
  };

  const updateSelectedObject = (updater: (obj: ObjectModel) => ObjectModel) => {
    if (selection.kind !== "object") return;
    setData((prev) => ({
      ...prev,
      objects: prev.objects.map((obj) => (obj.id === selection.objectId ? updater(obj) : obj)),
    }));
  };

  const updateSelectedCable = (updater: (cable: CableModel) => CableModel) => {
    if (selection.kind !== "cable") return;
    setData((prev) => ({
      ...prev,
      cables: prev.cables.map((cable) => (cable.id === selection.cableId ? updater(cable) : cable)),
    }));
  };

  const selectedObject = useMemo(
    () => (selection.kind === "object" ? data.objects.find((o) => o.id === selection.objectId) ?? null : null),
    [selection, data.objects],
  );
  const selectedCable = useMemo(
    () =>
      selection.kind === "cable" || selection.kind === "cable-segment"
        ? data.cables.find((c) => c.id === selection.cableId) ?? null
        : null,
    [selection, data.cables],
  );

  const deleteCableSegment = (cableId: string, segmentIndex: number) => {
    setData((prev) => ({
      ...prev,
      cables: prev.cables.flatMap((cable) => {
        if (cable.id !== cableId) {
          return [cable];
        }
        if (cable.points.length <= 2) {
          return [];
        }
        const nextPoints = [...cable.points];
        nextPoints.splice(segmentIndex, 1);
        return [{ ...cable, points: nextPoints }];
      }),
    }));
    const cable = data.cables.find((item) => item.id === cableId);
    if (cable && cable.points.length <= 2) {
      setSelection({ kind: "none" });
    } else {
      setSelection({ kind: "cable", cableId });
    }
  };

  const deleteCablePoint = (cableId: string, pointIndex: number) => {
    setData((prev) => ({
      ...prev,
      cables: prev.cables.flatMap((cable) => {
        if (cable.id !== cableId) {
          return [cable];
        }
        if (cable.points.length <= 2) {
          return [];
        }
        const nextPoints = [...cable.points];
        nextPoints.splice(pointIndex, 1);
        return [{ ...cable, points: nextPoints }];
      }),
    }));
    setSelection({ kind: "none" });
  };

  const startDrag = (
    mode: DragMode,
    event: React.PointerEvent<SVGElement>,
    targetId: string,
    opts: Omit<DragState, "mode" | "roomPosStart" | "targetId"> = {},
  ) => {
    if (!activeRoom) return;
    const roomPos = toRoomCoords(event as unknown as React.PointerEvent<SVGSVGElement>);
    if (!roomPos) return;
    (event.currentTarget as SVGElement).setPointerCapture(event.pointerId);
    setDragState({
      mode,
      roomPosStart: roomPos,
      targetId,
      ...opts,
    });
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!dragState || !activeRoom) return;
    const pos = toRoomCoords(event);
    if (!pos) return;
    const dx = pos.x - dragState.roomPosStart.x;
    const dy = pos.y - dragState.roomPosStart.y;

    if (dragState.mode === "wall-point" && typeof dragState.index === "number") {
      updateRoom(dragState.targetId, (room) => {
        const next = [...room.wallPoints];
        next[dragState.index as number] = roundPoint(snapToGrid ? snapPoint(pos, room.gridSizeMeters) : pos);
        return { ...room, wallPoints: next };
      });
      return;
    }
    if (dragState.mode === "wall-edge" && typeof dragState.index === "number" && dragState.initialPoint && dragState.secondaryPoint) {
      const edgeIndex = dragState.index;
      updateRoom(dragState.targetId, (room) => {
        const next = [...room.wallPoints];
        next[edgeIndex] = {
          x: roundCoord(clamp(dragState.initialPoint!.x + dx, 0, room.widthMeters)),
          y: roundCoord(clamp(dragState.initialPoint!.y + dy, 0, room.heightMeters)),
        };
        next[(edgeIndex + 1) % next.length] = {
          x: roundCoord(clamp(dragState.secondaryPoint!.x + dx, 0, room.widthMeters)),
          y: roundCoord(clamp(dragState.secondaryPoint!.y + dy, 0, room.heightMeters)),
        };
        return { ...room, wallPoints: next };
      });
      return;
    }
    if (dragState.mode === "object-move" && dragState.initialObject) {
      setData((prev) => ({
        ...prev,
        objects: prev.objects.map((obj) => {
          if (obj.id !== dragState.targetId) return obj;
          const next = {
            ...obj,
            x: roundCoord(clamp(dragState.initialObject!.x + dx, 0, activeRoom.widthMeters - obj.width)),
            y: roundCoord(clamp(dragState.initialObject!.y + dy, 0, activeRoom.heightMeters - obj.height)),
          };
          return snapToGrid
            ? {
                ...next,
                x: roundCoord(
                  Math.max(
                    0,
                    Math.min(activeRoom.widthMeters - next.width, Math.round(next.x / activeRoom.gridSizeMeters) * activeRoom.gridSizeMeters),
                  ),
                ),
                y: roundCoord(
                  Math.max(
                    0,
                    Math.min(activeRoom.heightMeters - next.height, Math.round(next.y / activeRoom.gridSizeMeters) * activeRoom.gridSizeMeters),
                  ),
                ),
              }
            : next;
        }),
      }));
      return;
    }
    if (dragState.mode === "object-resize" && dragState.initialObject) {
      setData((prev) => ({
        ...prev,
        objects: prev.objects.map((obj) => {
          if (obj.id !== dragState.targetId) return obj;
          const width = roundCoord(clamp(dragState.initialObject!.width + dx, 0.4, activeRoom.widthMeters - obj.x));
          const height = roundCoord(clamp(dragState.initialObject!.height + dy, 0.4, activeRoom.heightMeters - obj.y));
          return { ...obj, width, height };
        }),
      }));
      return;
    }
    if (dragState.mode === "cable-point" && typeof dragState.index === "number") {
      setData((prev) => ({
        ...prev,
        cables: prev.cables.map((cable) => {
          if (cable.id !== dragState.targetId) return cable;
          const nextPoints = [...cable.points];
          const nextPoint = roundPoint(snapToGrid ? snapPoint(pos, activeRoom.gridSizeMeters) : pos);
          nextPoints[dragState.index as number] = {
            ...nextPoints[dragState.index as number],
            x: nextPoint.x,
            y: nextPoint.y,
          };
          if (cable.lengthMode === "fixed") {
            const baselinePoints = dragState.initialCablePoints ?? cable.points;
            const lockedLength = cable.fixedLengthMeters ?? calculatePolylineLength(baselinePoints);
            return { ...cable, points: nextPoints, fixedLengthMeters: lockedLength };
          }
          return { ...cable, points: nextPoints };
        }),
      }));
    }
  };

  const handlePointerUp = () => {
    if (dragState?.mode === "cable-point" && typeof dragState.index === "number") {
      let moveResult: FixedRouteReconcileResult | null = null;
      setData((prev) => ({
        ...prev,
        cables: prev.cables.map((cable) => {
          if (cable.id !== dragState.targetId || cable.lengthMode !== "fixed") {
            return cable;
          }
          const baselinePoints = dragState.initialCablePoints ?? cable.points;
          const baselineCable: CableModel = {
            ...cable,
            points: baselinePoints,
          };
          const lockedLength = cable.fixedLengthMeters ?? calculatePolylineLength(baselinePoints);
          const currentLength = calculatePolylineLength(cable.points);
          if (Math.abs(currentLength - lockedLength) <= FIXED_LENGTH_TOLERANCE_METERS) {
            moveResult = {
              points: cable.points,
              status: "exact",
              lengthGapMeters: roundCoord(lockedLength - currentLength),
              insertedPoints: 0,
            };
            return { ...cable, fixedLengthMeters: lockedLength };
          }
          const reconciled = reconcileFixedLengthRoute(baselineCable, dragState.index as number, cable.points);
          moveResult = reconciled;
          return { ...cable, points: reconciled.points, fixedLengthMeters: lockedLength };
        }),
      }));
      if (moveResult) {
        setStatus(fixedLengthStatusMessage("move", moveResult));
      }
    }
    if (dragState) {
      setDragState(null);
    }
  };

  const exportJson = () => {
    const blob = new Blob([exportProjectJson(data)], { type: "application/json" });
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = "2d-map-project.json";
    link.click();
    URL.revokeObjectURL(href);
    setStatus("Exported project JSON.");
  };

  const onImportClick = () => {
    fileInputRef.current?.click();
  };

  const onImportFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const result = String(reader.result ?? "");
        const imported = importProjectJson(result);
        setData(imported);
        setSelection({ kind: "none" });
        setStatus("Project JSON imported.");
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown import error.";
        setStatus(`Import failed: ${message}`);
      }
    };
    reader.readAsText(file);
    event.target.value = "";
  };

  const onActiveRoomChange = (roomId: string) => {
    setData((prev) => ({ ...prev, activeRoomId: roomId }));
    setInsertWallPointMode(false);
    setSelection({ kind: "none" });
  };

  const insertCableBendPoint = (cableId: string, toPointIndex: number, clickPoint: Point) => {
    if (!activeRoom) return;
    const nextClickPoint = roundPoint(snapToGrid ? snapPoint(clickPoint, activeRoom.gridSizeMeters) : clickPoint);
    let inserted = false;
    let bendResult: FixedRouteReconcileResult | null = null;
    setData((prev) => ({
      ...prev,
      cables: prev.cables.map((cable) => {
        if (cable.id !== cableId) return cable;
        const nextPoints = [...cable.points];
        nextPoints.splice(toPointIndex, 0, {
          roomId: activeRoom.id,
          x: nextClickPoint.x,
          y: nextClickPoint.y,
        });
        if (cable.lengthMode === "fixed") {
          const lockedLength = cable.fixedLengthMeters ?? calculatePolylineLength(cable.points);
          const reconciled = reconcileFixedLengthRoute(cable, Math.max(0, toPointIndex - 1), nextPoints);
          inserted = true;
          bendResult = reconciled;
          return { ...cable, points: reconciled.points, fixedLengthMeters: lockedLength };
        }
        inserted = true;
        return { ...cable, points: nextPoints };
      }),
    }));
    if (bendResult) {
      setStatus(fixedLengthStatusMessage("bend", bendResult));
    } else if (inserted) {
      setStatus("Inserted bend point on cable segment.");
    }
  };

  const removeSelected = () => {
    if (selection.kind === "object") {
      setData((prev) => ({ ...prev, objects: prev.objects.filter((obj) => obj.id !== selection.objectId) }));
      setSelection({ kind: "none" });
      return;
    }
    if (selection.kind === "cable-segment") {
      deleteCableSegment(selection.cableId, selection.segmentIndex);
      return;
    }
    if (selection.kind === "cable" && typeof selection.pointIndex === "number") {
      deleteCablePoint(selection.cableId, selection.pointIndex);
      return;
    }
    if (selection.kind === "cable") {
      const confirmDelete = window.confirm("Delete this cable?");
      if (!confirmDelete) {
        return;
      }
      setData((prev) => ({ ...prev, cables: prev.cables.filter((cable) => cable.id !== selection.cableId) }));
      setSelection({ kind: "none" });
    }
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const targetTag = (event.target as HTMLElement | null)?.tagName;
      if (targetTag === "INPUT" || targetTag === "TEXTAREA" || targetTag === "SELECT") {
        return;
      }
      if (event.key !== "Delete" && event.key !== "Backspace") {
        return;
      }
      if (selection.kind === "cable-segment") {
        event.preventDefault();
        deleteCableSegment(selection.cableId, selection.segmentIndex);
        return;
      }
      if (selection.kind === "cable" && typeof selection.pointIndex === "number") {
        event.preventDefault();
        deleteCablePoint(selection.cableId, selection.pointIndex);
        return;
      }
      if (selection.kind === "cable") {
        event.preventDefault();
        const confirmDelete = window.confirm("Delete this cable?");
        if (!confirmDelete) {
          return;
        }
        setData((prev) => ({ ...prev, cables: prev.cables.filter((cable) => cable.id !== selection.cableId) }));
        setSelection({ kind: "none" });
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selection, deleteCableSegment, deleteCablePoint]);

  return (
    <div className="app-shell">
      <header className="top-bar">
        <h1>2D Cable Planning Map</h1>
        <div className="top-controls">
          <label className="room-select-label">
            Active room:
            <select
              className="room-select"
              value={data.activeRoomId ?? ""}
              onChange={(event) => onActiveRoomChange(event.target.value)}
              title={activeRoom?.name ?? ""}
            >
              {data.rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.name}
                </option>
              ))}
            </select>
          </label>
          <button type="button" onClick={exportJson}>
            Export JSON
          </button>
          <button type="button" onClick={onImportClick}>
            Import JSON
          </button>
          <button
            type="button"
            onClick={() => {
              clearDraft();
              setData(createInitialData());
              setSelection({ kind: "none" });
              setCableDraft(null);
              setStatus("Reset editor and cleared local draft.");
            }}
          >
            Reset
          </button>
          <input ref={fileInputRef} type="file" accept="application/json" onChange={onImportFileChange} style={{ display: "none" }} />
        </div>
      </header>

      <div className="content">
        <aside className="left-panel">
          <section>
            <h2>Tool groups</h2>
            <div className="row-buttons">
              <button type="button" className={activeGroup === "room" ? "active" : ""} onClick={() => setActiveGroup("room")}>
                Room
              </button>
              <button type="button" className={activeGroup === "object" ? "active" : ""} onClick={() => setActiveGroup("object")}>
                Objects
              </button>
            </div>
            <ul className="tool-list">
              {TOOL_REGISTRY.filter((tool) => (activeGroup === "room" ? tool.group === "room" : tool.group !== "room")).map((tool) => (
                <li key={tool.id}>
                  <strong>{tool.label}</strong>
                  <span>{tool.description}</span>
                </li>
              ))}
            </ul>
          </section>

          {activeGroup === "room" && (
            <>
              <section>
                <h2>Room setup (selected room)</h2>
                {activeRoom ? (
                  <>
                    <label>
                      Name
                      <input
                        value={activeRoom.name}
                        onChange={(event) => updateSelectedRoom((room) => ({ ...room, name: event.target.value }))}
                      />
                    </label>
                    <label>
                      Width (m)
                      <input
                        type="number"
                        min={1}
                        step={0.5}
                        value={activeRoom.widthMeters}
                        onChange={(event) => {
                          const parsed = Number(event.target.value);
                          if (!Number.isFinite(parsed)) {
                            return;
                          }
                          updateSelectedRoom((room) => ({ ...room, widthMeters: roundCoord(Math.max(1, parsed)) }));
                        }}
                      />
                    </label>
                    <label>
                      Height (m)
                      <input
                        type="number"
                        min={1}
                        step={0.5}
                        value={activeRoom.heightMeters}
                        onChange={(event) => {
                          const parsed = Number(event.target.value);
                          if (!Number.isFinite(parsed)) {
                            return;
                          }
                          updateSelectedRoom((room) => ({ ...room, heightMeters: roundCoord(Math.max(1, parsed)) }));
                        }}
                      />
                    </label>
                  </>
                ) : (
                  <p>No active room selected.</p>
                )}
              </section>

              <section>
                <h2>Create new room</h2>
                <label>
                  Name
                  <input value={newRoomName} onChange={(event) => setNewRoomName(event.target.value)} />
                </label>
                <label>
                  Width (m)
                  <input type="number" min={1} step={0.5} value={newRoomWidth} onChange={(event) => setNewRoomWidth(Number(event.target.value))} />
                </label>
                <label>
                  Height (m)
                  <input type="number" min={1} step={0.5} value={newRoomHeight} onChange={(event) => setNewRoomHeight(Number(event.target.value))} />
                </label>
                <button type="button" onClick={addRoom}>
                  Add room
                </button>
              </section>

              {activeRoom && (
                <section key={`${activeRoom.id}-room-properties`}>
                  <h2>Room properties</h2>
                  <label>
                    Grid size (m)
                    <input
                      type="number"
                      min={0.1}
                      step={0.1}
                      value={activeRoom.gridSizeMeters}
                      onChange={(event) =>
                        updateRoom(activeRoom.id, (room) => ({
                          ...room,
                          gridSizeMeters: roundCoord(Math.max(0.1, Number(event.target.value))),
                        }))
                      }
                    />
                  </label>
                  <label>
                    Background
                    <input
                      type="color"
                      value={activeRoom.background}
                      onChange={(event) => updateRoom(activeRoom.id, (room) => ({ ...room, background: event.target.value }))}
                    />
                  </label>
                  <button
                    type="button"
                    className={insertWallPointMode ? "active" : ""}
                    onClick={() => {
                      setInsertWallPointMode((prev) => !prev);
                      setDividerWallDraft(null);
                    }}
                  >
                    {insertWallPointMode ? "Stop inserting wall points" : "Insert wall point on outer wall"}
                  </button>
                  <button type="button" onClick={addWallSegment}>
                    Add outer wall segment point
                  </button>
                </section>
              )}
            </>
          )}

          {activeGroup === "object" && (
            <>
              {activeRoom && (
                <section key={activeRoom.id}>
                  <h2>Wall tools</h2>
                  <label className="checkbox-row">
                    <input type="checkbox" checked={snapToGrid} onChange={(event) => setSnapToGrid(event.target.checked)} />
                    Snap to grid
                  </label>
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={showWallSegmentLengths}
                      onChange={(event) => setShowWallSegmentLengths(event.target.checked)}
                    />
                    Show wall segment lengths
                  </label>
                  <button
                    type="button"
                    className={dividerWallDraft !== null ? "active" : ""}
                    onClick={() => {
                      setDividerWallDraft((prev) => (prev === null ? { x: Number.NaN, y: Number.NaN } : null));
                      setInsertWallPointMode(false);
                    }}
                  >
                    {dividerWallDraft !== null ? "Cancel divider wall" : "Add room divider wall"}
                  </button>
                  <small>Click two points in the room to place a standalone divider wall.</small>
                </section>
              )}

              <section>
                <h2>Object palette</h2>
                <div className="row-buttons">
                  <button type="button" onClick={() => addObject("square")}>
                    Square
                  </button>
                  <button type="button" onClick={() => addObject("rectangle")}>
                    Rectangle
                  </button>
                  <button type="button" onClick={() => addObject("circle")}>
                    Circle
                  </button>
                </div>
              </section>

              <section>
                <h2>Cable palette</h2>
                {cableDraft ? (
                  <>
                    <label>
                      Type
                      <select
                        value={cableDraft.type}
                        onChange={(event) =>
                          setCableDraft((prev) => (prev ? { ...prev, type: event.target.value as CableType } : prev))
                        }
                      >
                        <option value="network">Network (grey)</option>
                        <option value="power230">Power 230V (black)</option>
                        <option value="power400">Power 400V (black)</option>
                        <option value="fiber">Fibre (dark yellow)</option>
                      </select>
                    </label>
                    <label>
                      Tag
                      <input value={cableDraft.tag} onChange={(event) => setCableDraft((prev) => (prev ? { ...prev, tag: event.target.value } : prev))} />
                    </label>
                    <label>
                      Label
                      <input value={cableDraft.label} onChange={(event) => setCableDraft((prev) => (prev ? { ...prev, label: event.target.value } : prev))} />
                    </label>
                    <label>
                      Comment
                      <input value={cableDraft.comment} onChange={(event) => setCableDraft((prev) => (prev ? { ...prev, comment: event.target.value } : prev))} />
                    </label>
                    <label>
                      Diameter (mm)
                      <input
                        type="number"
                        min={1}
                        value={cableDraft.diameterMm}
                        onChange={(event) => setCableDraft((prev) => (prev ? { ...prev, diameterMm: Math.max(1, Number(event.target.value)) } : prev))}
                      />
                    </label>
                    <div className="row-buttons">
                      <button type="button" onClick={finishCableDraft}>
                        Finish cable
                      </button>
                      <button type="button" onClick={cancelCableDraft}>
                        Cancel
                      </button>
                    </div>
                    <small>Points: {cableDraft.points.length} (click in room to add)</small>
                  </>
                ) : (
                  <div className="row-buttons">
                    <button type="button" onClick={() => startCableDraft("network")}>
                      New network
                    </button>
                    <button type="button" onClick={() => startCableDraft("power230")}>
                      New power
                    </button>
                    <button type="button" onClick={() => startCableDraft("fiber")}>
                      New fiber
                    </button>
                  </div>
                )}
                <small>Tip: double-click a cable segment to insert a bend point.</small>
              </section>
            </>
          )}
        </aside>

        <main className="canvas-container">
          {activeRoom ? (
            <>
              <div className="canvas-controls">
                <button type="button" onClick={() => setZoom((z) => clamp(z - 0.1, 0.4, 3))}>
                  -
                </button>
                <span>Zoom {zoom.toFixed(1)}x</span>
                <button type="button" onClick={() => setZoom((z) => clamp(z + 0.1, 0.4, 3))}>
                  +
                </button>
                <button type="button" onClick={() => setPan((prev) => ({ ...prev, x: prev.x - 15 }))}>
                  ◀
                </button>
                <button type="button" onClick={() => setPan((prev) => ({ ...prev, y: prev.y - 15 }))}>
                  ▲
                </button>
                <button type="button" onClick={() => setPan((prev) => ({ ...prev, y: prev.y + 15 }))}>
                  ▼
                </button>
                <button type="button" onClick={() => setPan((prev) => ({ ...prev, x: prev.x + 15 }))}>
                  ▶
                </button>
              </div>
              <svg
                ref={svgRef}
                className="workspace"
                onClick={handleCanvasClick}
                onPointerMove={handlePointerMove}
                onPointerUp={handlePointerUp}
                onPointerCancel={handlePointerUp}
              >
                <g transform={`translate(${pan.x},${pan.y}) scale(${zoom * METERS_TO_PX})`}>
                  <rect x={0} y={0} width={activeRoom.widthMeters} height={activeRoom.heightMeters} fill={activeRoom.background} stroke="#ced4da" strokeWidth={0.03} />

                  {Array.from({ length: Math.floor(activeRoom.widthMeters / activeRoom.gridSizeMeters) + 1 }).map((_, index) => {
                    const x = index * activeRoom.gridSizeMeters;
                    return (
                      <line key={`gx-${x}`} x1={x} y1={0} x2={x} y2={activeRoom.heightMeters} stroke="#e9ecef" strokeWidth={0.01} />
                    );
                  })}
                  {Array.from({ length: Math.floor(activeRoom.heightMeters / activeRoom.gridSizeMeters) + 1 }).map((_, index) => {
                    const y = index * activeRoom.gridSizeMeters;
                    return (
                      <line key={`gy-${y}`} x1={0} y1={y} x2={activeRoom.widthMeters} y2={y} stroke="#e9ecef" strokeWidth={0.01} />
                    );
                  })}

                  <polygon points={toPointsAttribute(activeRoom.wallPoints)} fill="none" stroke="#1f2937" strokeWidth={0.05} />

                  {activeRoom.dividerWalls.map((segment, index) => (
                    <line
                      key={`divider-wall-${index}`}
                      x1={segment.from.x}
                      y1={segment.from.y}
                      x2={segment.to.x}
                      y2={segment.to.y}
                      stroke="#475569"
                      strokeWidth={0.06}
                    />
                  ))}

                  {dividerWallDraft && Number.isFinite(dividerWallDraft.x) && Number.isFinite(dividerWallDraft.y) && (
                    <line
                      x1={dividerWallDraft.x}
                      y1={dividerWallDraft.y}
                      x2={dividerWallDraft.x}
                      y2={dividerWallDraft.y}
                      stroke="#0ea5e9"
                      strokeWidth={0.04}
                      strokeDasharray="0.1 0.05"
                    />
                  )}

                  {activeRoom.wallPoints.map((point, index) => (
                    <g key={`wall-${index}`}>
                      <line
                        x1={point.x}
                        y1={point.y}
                        x2={activeRoom.wallPoints[(index + 1) % activeRoom.wallPoints.length].x}
                        y2={activeRoom.wallPoints[(index + 1) % activeRoom.wallPoints.length].y}
                        stroke="transparent"
                        strokeWidth={0.35}
                        onPointerDown={(event) => {
                          event.stopPropagation();
                          const next = activeRoom.wallPoints[(index + 1) % activeRoom.wallPoints.length];
                          setSelection({ kind: "wall-edge", roomId: activeRoom.id, edgeIndex: index });
                          startDrag("wall-edge", event, activeRoom.id, {
                            index,
                            initialPoint: point,
                            secondaryPoint: next,
                          });
                        }}
                      />
                      <circle
                        cx={point.x}
                        cy={point.y}
                        r={0.09}
                        fill={selection.kind === "wall-point" && selection.pointIndex === index ? "#0ea5e9" : "#111827"}
                        onPointerDown={(event) => {
                          event.stopPropagation();
                          setSelection({ kind: "wall-point", roomId: activeRoom.id, pointIndex: index });
                          startDrag("wall-point", event, activeRoom.id, { index });
                        }}
                      />
                      {showWallSegmentLengths && (
                        <text
                          x={(point.x + activeRoom.wallPoints[(index + 1) % activeRoom.wallPoints.length].x) / 2}
                          y={(point.y + activeRoom.wallPoints[(index + 1) % activeRoom.wallPoints.length].y) / 2}
                          fontSize={0.18}
                          fill="#0f172a"
                          textAnchor="middle"
                          dominantBaseline="middle"
                          style={{ pointerEvents: "none" }}
                        >
                          {distance(point, activeRoom.wallPoints[(index + 1) % activeRoom.wallPoints.length]).toFixed(2)}m
                        </text>
                      )}
                    </g>
                  ))}

                  {roomObjects.map((obj) => (
                    <g key={obj.id}>
                      {obj.shape === "circle" ? (
                        <ellipse
                          cx={obj.x + obj.width / 2}
                          cy={obj.y + obj.height / 2}
                          rx={obj.width / 2}
                          ry={obj.height / 2}
                          fill="#c7d2fe"
                          stroke={selection.kind === "object" && selection.objectId === obj.id ? "#1d4ed8" : "#4338ca"}
                          strokeWidth={0.05}
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelection({ kind: "object", objectId: obj.id });
                          }}
                          onPointerDown={(event) => {
                            event.stopPropagation();
                            setSelection({ kind: "object", objectId: obj.id });
                            startDrag("object-move", event, obj.id, {
                              initialObject: { x: obj.x, y: obj.y, width: obj.width, height: obj.height },
                            });
                          }}
                        />
                      ) : (
                        <rect
                          x={obj.x}
                          y={obj.y}
                          width={obj.width}
                          height={obj.height}
                          fill="#c7d2fe"
                          stroke={selection.kind === "object" && selection.objectId === obj.id ? "#1d4ed8" : "#4338ca"}
                          strokeWidth={0.05}
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelection({ kind: "object", objectId: obj.id });
                          }}
                          onPointerDown={(event) => {
                            event.stopPropagation();
                            setSelection({ kind: "object", objectId: obj.id });
                            startDrag("object-move", event, obj.id, {
                              initialObject: { x: obj.x, y: obj.y, width: obj.width, height: obj.height },
                            });
                          }}
                        />
                      )}
                      <rect
                        x={obj.x + obj.width - 0.12}
                        y={obj.y + obj.height - 0.12}
                        width={0.16}
                        height={0.16}
                        fill="#1d4ed8"
                        onClick={(event) => {
                          event.stopPropagation();
                          setSelection({ kind: "object", objectId: obj.id });
                        }}
                        onPointerDown={(event) => {
                          event.stopPropagation();
                          setSelection({ kind: "object", objectId: obj.id });
                          startDrag("object-resize", event, obj.id, {
                            initialObject: { x: obj.x, y: obj.y, width: obj.width, height: obj.height },
                          });
                        }}
                      />
                      <text x={obj.x} y={obj.y - 0.08} fontSize={0.22} fill="#0f172a">
                        {obj.label || obj.name}
                      </text>
                    </g>
                  ))}

                  {activeRoomCables.map((cable) => {
                    const inRoomSegments: Array<{ from: RoomPoint; to: RoomPoint; index: number }> = [];
                    const isCableSelected = selection.kind === "cable" && selection.cableId === cable.id;
                    for (let i = 1; i < cable.points.length; i += 1) {
                      const from = cable.points[i - 1];
                      const to = cable.points[i];
                      if (from.roomId === activeRoom.id && to.roomId === activeRoom.id) {
                        inRoomSegments.push({ from, to, index: i });
                      }
                    }
                    return (
                      <g key={cable.id}>
                        {inRoomSegments.map((segment) => (
                          <g key={`${cable.id}-${segment.index}`}>
                            {isCableSelected && (
                              <line
                                x1={segment.from.x}
                                y1={segment.from.y}
                                x2={segment.to.x}
                                y2={segment.to.y}
                                stroke="#0ea5e9"
                                strokeOpacity={0.35}
                                strokeWidth={0.16}
                                pointerEvents="none"
                              />
                            )}
                            <line
                              x1={segment.from.x}
                              y1={segment.from.y}
                              x2={segment.to.x}
                              y2={segment.to.y}
                              stroke={cable.color}
                              strokeWidth={isCableSelected ? 0.08 : 0.06}
                              onClick={(event) => {
                                event.stopPropagation();
                                setSelection({ kind: "cable-segment", cableId: cable.id, segmentIndex: segment.index });
                              }}
                              onDoubleClick={(event) => {
                                event.stopPropagation();
                                const roomPoint = toRoomCoords(event);
                                if (!roomPoint) {
                                  return;
                                }
                                setSelection({ kind: "cable", cableId: cable.id });
                                insertCableBendPoint(cable.id, segment.index, roomPoint);
                              }}
                            />
                          </g>
                        ))}
                        {cable.points.map((point, index) =>
                          point.roomId === activeRoom.id ? (
                            <circle
                              key={`${cable.id}-pt-${index}`}
                              cx={point.x}
                              cy={point.y}
                              r={isCableSelected ? 0.09 : 0.08}
                              fill={selection.kind === "cable" && selection.cableId === cable.id && selection.pointIndex === index ? "#ef4444" : cable.color}
                              stroke={isCableSelected ? "#0ea5e9" : "transparent"}
                              strokeWidth={isCableSelected ? 0.03 : 0}
                              onPointerDown={(event) => {
                                event.stopPropagation();
                                setSelection({ kind: "cable", cableId: cable.id, pointIndex: index });
                                startDrag("cable-point", event, cable.id, {
                                  index,
                                  initialCablePoints: cable.points.map((existingPoint) => ({ ...existingPoint })),
                                });
                              }}
                            />
                          ) : null,
                        )}
                      </g>
                    );
                  })}

                  {cableDraft &&
                    cableDraft.points
                      .filter((point) => point.roomId === activeRoom.id)
                      .map((point, index) => (
                        <circle key={`draft-${index}`} cx={point.x} cy={point.y} r={0.07} fill={getCableColor(cableDraft.type)} />
                      ))}
                </g>
              </svg>
            </>
          ) : (
            <p>No room selected.</p>
          )}
        </main>

        <aside className="right-panel">
          <section>
            <h2>Selection</h2>
            <p>
              {selection.kind === "none"
                ? "Nothing selected"
                : selection.kind === "cable" && typeof selection.pointIndex === "number"
                  ? "cable point"
                  : selection.kind === "cable-segment"
                    ? "cable segment"
                    : selection.kind}
            </p>
            {selection.kind === "cable-segment" && (
              <button type="button" onClick={removeSelected}>
                Delete selected segment
              </button>
            )}
            {selection.kind === "cable" && typeof selection.pointIndex === "number" && (
              <button type="button" onClick={removeSelected}>
                Delete selected point
              </button>
            )}
            {(selection.kind === "object" || (selection.kind === "cable" && typeof selection.pointIndex !== "number")) && (
              <button type="button" onClick={removeSelected}>
                Delete selected
              </button>
            )}
          </section>

          {selectedObject && (
            <section>
              <h2>Object properties</h2>
              <label>
                Name
                <input value={selectedObject.name} onChange={(event) => updateSelectedObject((obj) => ({ ...obj, name: event.target.value }))} />
              </label>
              <label>
                Label
                <input value={selectedObject.label} onChange={(event) => updateSelectedObject((obj) => ({ ...obj, label: event.target.value }))} />
              </label>
              <label>
                Comment
                <input value={selectedObject.comment} onChange={(event) => updateSelectedObject((obj) => ({ ...obj, comment: event.target.value }))} />
              </label>
              <label>
                Width (m)
                <input
                  type="number"
                  min={0.2}
                  step={0.1}
                  value={selectedObject.width}
                  onChange={(event) => updateSelectedObject((obj) => ({ ...obj, width: roundCoord(Math.max(0.2, Number(event.target.value))) }))}
                />
              </label>
              <label>
                Height (m)
                <input
                  type="number"
                  min={0.2}
                  step={0.1}
                  value={selectedObject.height}
                  onChange={(event) => updateSelectedObject((obj) => ({ ...obj, height: roundCoord(Math.max(0.2, Number(event.target.value))) }))}
                />
              </label>
            </section>
          )}

          {selectedCable && (
            <section>
              <h2>Cable properties</h2>
              <label>
                Tag
                <input value={selectedCable.tag} onChange={(event) => updateSelectedCable((cable) => ({ ...cable, tag: event.target.value }))} />
              </label>
              <label>
                Label
                <input value={selectedCable.label} onChange={(event) => updateSelectedCable((cable) => ({ ...cable, label: event.target.value }))} />
              </label>
              <label>
                Comment
                <input value={selectedCable.comment} onChange={(event) => updateSelectedCable((cable) => ({ ...cable, comment: event.target.value }))} />
              </label>
              <label>
                Type
                <select
                  value={selectedCable.type}
                  onChange={(event) =>
                    updateSelectedCable((cable) => {
                      const type = event.target.value as CableType;
                      return { ...cable, type, color: getCableColor(type) };
                    })
                  }
                >
                  <option value="network">network</option>
                  <option value="power230">230V power</option>
                  <option value="power400">400V power</option>
                  <option value="fiber">fiber</option>
                </select>
              </label>
              <label>
                Diameter (mm)
                <input
                  type="number"
                  min={1}
                  value={selectedCable.diameterMm}
                  onChange={(event) => updateSelectedCable((cable) => ({ ...cable, diameterMm: Math.max(1, Number(event.target.value)) }))}
                />
              </label>
              <label>
                Length mode
                <select
                  value={selectedCable.lengthMode}
                  onChange={(event) =>
                    updateSelectedCable((cable) => {
                      const mode = event.target.value as CableModel["lengthMode"];
                      if (mode === "fixed") {
                        return {
                          ...cable,
                          lengthMode: mode,
                          fixedLengthMeters: cable.fixedLengthMeters ?? calculatePolylineLength(cable.points),
                        };
                      }
                      if (mode === "dynamic") {
                        return { ...cable, lengthMode: mode, fixedLengthMeters: cable.fixedLengthMeters };
                      }
                      return { ...cable, lengthMode: mode };
                    })
                  }
                >
                  <option value="dynamic">Dynamic</option>
                  <option value="fixed">Fixed</option>
                </select>
              </label>
              {selectedCable.lengthMode === "fixed" && (
                <>
                  <div>Locked total length: {(selectedCable.fixedLengthMeters ?? calculatePolylineLength(selectedCable.points)).toFixed(2)} m</div>
                  <div>Current route geometry length: {calculatePolylineLength(selectedCable.points).toFixed(2)} m</div>
                  {Math.abs((selectedCable.fixedLengthMeters ?? calculatePolylineLength(selectedCable.points)) - calculatePolylineLength(selectedCable.points)) >
                    STAPLED_MATCH_TOLERANCE_METERS && (
                    <div>
                      Length warning: route differs from locked total by{" "}
                      {Math.abs((selectedCable.fixedLengthMeters ?? calculatePolylineLength(selectedCable.points)) - calculatePolylineLength(selectedCable.points)).toFixed(2)}{" "}
                      m.
                    </div>
                  )}
                </>
              )}
              <label>
                Bend radii (m, comma separated)
                <input
                  value={selectedCable.bendRadiusMeters.join(",")}
                  onChange={(event) =>
                    updateSelectedCable((cable) => ({
                      ...cable,
                      bendRadiusMeters: event.target.value
                        .split(",")
                        .map((entry) => Number(entry.trim()))
                        .filter((entry) => Number.isFinite(entry) && entry >= 0)
                        .map((entry) => roundCoord(entry)),
                    }))
                  }
                />
              </label>

              <div className="stats">
                <div>Total length: {cableLengthMeters(selectedCable).toFixed(2)} m</div>
                <ul>
                  {selectedCable.points.slice(1).map((point, index) => {
                    const prev = selectedCable.points[index];
                    const length = segmentLengthMeters(prev, point);
                    const label = prev.roomId === point.roomId ? `${length.toFixed(2)} m` : "cross-room link";
                    return (
                      <li key={`${selectedCable.id}-seg-${index}`}>
                        Segment {index + 1}: {label}
                      </li>
                    );
                  })}
                </ul>
              </div>
            </section>
          )}

          <section>
            <h2>Status</h2>
            <p>{status}</p>
          </section>
        </aside>
      </div>
    </div>
  );
};

export default App;
