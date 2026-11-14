export type ToolDefinition = {
  id: string;
  group: "room" | "object" | "cable";
  label: string;
  description: string;
};

export const TOOL_REGISTRY: ToolDefinition[] = [
  {
    id: "room-create",
    group: "room",
    label: "Create room",
    description: "Create a room with width/height and editable walls.",
  },
  {
    id: "room-wall-edit",
    group: "room",
    label: "Edit outer walls",
    description: "Insert and drag wall points or wall sections along the room boundary.",
  },
  {
    id: "object-shape-add",
    group: "object",
    label: "Add divider walls",
    description: "Place standalone internal wall segments that divide the room.",
  },
  {
    id: "object-edit",
    group: "object",
    label: "Edit object",
    description: "Move, resize, and edit object metadata.",
  },
  {
    id: "cable-add",
    group: "cable",
    label: "Add cable",
    description: "Create multi-segment cables with typed properties.",
  },
  {
    id: "cable-edit",
    group: "cable",
    label: "Edit cable",
    description: "Drag route points and switch length mode.",
  },
];
