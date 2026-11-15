# 2D-map Python (PySide6)

Desktop rewrite of the TypeScript 2D cable planning editor, implemented with PySide6.

## Features

- Room creation from width/height
- Wall-point editing and edge point insertion
- Divider wall segment tool
- Object tools (square, rectangle, circle) with drag/drop move and size editing
- Cable routing with multi-point placement
- Cable segment point insertion for bend shaping
- Cable metadata and type colors:
  - network: gray
  - power230/power400: black
  - fiber: dark yellow
- Cable length mode:
  - dynamic: recalculates from geometry
  - fixed: uses locked fixed length value
- JSON import/export and autosave draft persistence

## Bugs, faults and improvements to be done:
1. Room: Add delete function for rooms, I should be able to put a tick mark on two or more rooms in a list and delete them.
2. Room: If a Room B exists and I press to create a new room, then maybe Room C would be better default naming. Ensure that new rooms are not by default created with identical names as that is confusing.
3. Room: Room name and name properties are the same, better to have building, floor and room name as properties.
4. Room: Placing a divider wall shall be similar to a cable except no curves/bends, just vertices. Refine the function so that one can create L-shaped dividers using several points and a placement mode and end placement function /end placement on right click.
5. Room: I need to be able to delete divider walls also.
6. Cable placement: still unable to move the points of the cables around.


## Requirements

- Python 3.11+
- PySide6

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Run

From [2D-map-python/](/home/john-tore/github/cable-routing/2D-map-python):

```bash
python main.py
```

If you use a virtual environment in the repository root:

```bash
/home/john-tore/github/cable-routing/.venv/bin/python main.py
```

## Controls

- Mouse wheel: zoom
- Middle-mouse drag: pan
- Room tab:
  - Create rooms
  - Edit walls mode for dragging wall points
  - Optional edge insertion mode for inserting wall points
  - Divider wall mode (click start + click end)
- Objects tab:
  - Add square/rectangle/circle
  - Select/move mode for dragging objects
  - Edit selected object properties in panel
- Cables tab:
  - Start cable placement, left-click points on canvas
  - Right-click or "Finish cable" to complete
  - Select cable segments and insert bend points
  - Edit selected cable properties and length mode

## Project JSON format

The app stores project data in JSON with top-level fields:

- `version` (currently `1`)
- `rooms[]`
- `objects[]`
- `cables[]`
- `activeRoomId`

This format is documented by the dataclass serializers in [models.py](/home/john-tore/github/cable-routing/2D-map-python/map2d/models.py).

## Draft autosave

Drafts are autosaved to:

- `~/.cable-routing-2d-map/draft.json`

You can clear it from **File -> Clear autosave draft**.

## Linux troubleshooting

If you see a crash like:

- `GLib-GIO-ERROR ... org.gnome.settings-daemon.plugins.xsettings ... 'antialiasing'`

the app now starts with desktop settings awareness disabled and Fusion style to avoid GNOME schema probing issues in mixed desktop setups.

If your environment still forces a problematic theme plugin, start with:

```bash
QT_QPA_PLATFORMTHEME=xdgdesktopportal python main.py
```
