# 2D map module for cable planning

The 2D map shall be based on Javascript, HTML, CSS etc.
The module shall have following functionality:

# TODO / Improvements to be done:
1. Currently there is no method to select the entire cable for deletion or changing properties.
2. The entire cable shall be selected when clicking on a cable line segment between the bend points.
3. The insert point and insert segment in room menu is the same, just merge it.



### Improvement status

All items above are now implemented in the React TypeScript tool:

1. **Wall segment lengths toggle** implemented (default hidden, available in wall tools).
2. **Object selection UX fixed**; plain click selects objects immediately and shows object properties.
3. **Room property sync fixed**; selected-room fields switch correctly with active room, with room creation in a dedicated section.
4. **2-decimal precision enforced** for room/object/cable coordinates and edited geometry values.
5. **Cable bend insertion improved** with **double-click on cable segment**.
6. **Fixed-length mode refined**; fixed length remains locked and manual total-length editing is removed.
7. **Top-level tabs consolidated** to **Room + Objects**.
8. **Room properties hidden on Objects tab** (shown on Room tab only).
9. **Objects tab now includes object, cable, and wall tools**, including explicit **Add wall segment** action.
10. **Fixed-length cable move assist rebuilt**; drag remains smooth (no live topology edits), segment lengths stay dynamic, and on release the editor reconciles toward locked **total** length using clamp + stapled-style assist. If exact lock cannot be matched, best-effort route is kept and an explicit length warning is shown.
11. **Cable selection UX improved**; selected cables are visually highlighted and remain selected when clicking empty canvas space (selection changes only when another selectable element is clicked).


## Create room: 
Create new rooms by first specifying an X and Y size in meters as basis, then an outline of the room (walls) is created and can be adjusted by inserting points along the outlined room. When additional points are placed, the outline is sectioned more and you can then drag the wall sections so that you get a custom shape.

The user can save the rooms and load rooms. The data for the rooms shall be stored in JSON format. Temporary data between saves can be stored in the browser.

A finished room is a coordinate system with default grid size 1.0 meter. The grid size shall be adjustable.

A light background color shall be default on the room, but customizable.

## General tool palette for adding objects in rooms:
A basis tool palette shall be available with basis shapes like square, circle, rectangles. The objects shall be adjustable in X / Y direction (size) and moveable within the rooms using drag and drop. A label can be added to each of the objects, and properties such as object name and comment shall be available for editing.

## Cable tool palette for adding cables to the rooms:
Cables of different types, network, power and fibre optical shall be created from a separate cable tool menu. The cables shall have properties: label/comment, tag/name, type (network, 230V power, 400V power), diameter(mm), color, total length in meters and segment lengths. The cables can go between rooms also, so they shall have datapoints and endpoints when placed that specifies room and coordinates for the segments within the rooms.

A cable placement tool shall be made to that a cable can have multiple segments and you shall be able to add bend radius to a corner.

The cables of different type shall be showed with colors: black for power, grey for network and dark yellow for fibre.

### Moving the cables around
The cables routes shall be modifyable with dragging and dropping, and the user shall be able to select whether to keep cable length as fixed length or dynamically calculate new length.

---

## Implemented MVP (React + TypeScript)

The module is implemented as a standalone frontend app in this folder with:

- **Framework:** React + TypeScript (Vite)
- **Workspace:** SVG-based editor with zoom/pan, grid rendering, and snap-to-grid
- **Room tools:** create room from width/height, edit wall points, drag wall sections, adjust grid and background color
- **Object tools:** add square/rectangle/circle, drag/resize in room, edit object metadata (name, label, comment)
- **Cable tools:** create typed multi-segment cables, drag route points, edit metadata, calculate total/segment lengths
- **Cable colors by type:**
  - Power (230V/400V): black
  - Network: grey
  - Fibre: dark yellow
- **Length behavior:** dynamic recalculation or fixed-length mode
- **Cross-room routing representation:** each cable datapoint stores `roomId + coordinates`
- **Persistence:** local browser draft autosave + JSON import/export
- **Extensibility:** modular tool registry for room/object/cable tool groups

## Directory layout

- `src/` – app code
  - `App.tsx` – editor shell, toolbars, room/object/cable workflows
  - `types.ts` – domain model types
  - `tooling/toolRegistry.ts` – modular toolbar/tool registrations
  - `utils/geometry.ts` – length/geometry helpers
  - `utils/json.ts` – JSON validation and import/export
  - `utils/storage.ts` – local-storage draft persistence

## Run locally

From `src/2D-map/`:

```bash
npm install
npm run dev
```

> Note: the module is pinned to **Vite 5.x** (`vite@5.4.21`, `@vitejs/plugin-react@4.3.4`) for compatibility with **Node.js 18.19.x**.

Build check:

```bash
npm run build
```
