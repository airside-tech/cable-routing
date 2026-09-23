# Cable Routing (JSON-Friendly)

This project provides patch-cable routing using a graph model and Dijkstra's algorithm.

It now supports:

- Auto routing (shortest path from source to target)
- Manual routing (shortest-path legs through ordered waypoints)
- JSON-safe import/export with explicit infinity handling (`"INF"`)
- Rack/panel/port selection filters before route solving
- U-height-aware patch ports (`1..47U`)
- Directional fixed inter-rack cables with IDs in `KX####` format

## Files

- `patching.py`: JSON helpers, topology helpers, selection filtering, and route APIs
- `dijkstra_v2.py`: reusable Dijkstra solver used by routing functions
- `tests.py`: unit tests for routing and JSON behavior

## Graph Model

The routing graph is a directed adjacency dictionary:

```python
graph = {
    "nodeA": {"nodeB": 1.2, "nodeC": 3.4},
    "nodeB": {"nodeC": 1.1},
    "nodeC": {}
}
```

- Keys are node IDs (`str`)
- Values are neighbor-weight maps (`dict[str, float]`)
- Weights must be numeric and non-negative

### Suggested node ID format

- Patch port: `rack:R1/panel:PP-A/port:01`
- Path segment: `rack:R1/path:vertical-left`
- Shared tray/path: `room:aisle-3/tray:T17`

## Patch Panel Metadata

Use metadata for filtering and integration:

```python
node_metadata = {
    "rack:R1/panel:PP-A/port:01": {
        "type": "patch_port",
        "rack": "R1",
        "panel": "PP-A",
        "port": "01",
        "status": "spare"
    }
}
```

Generate patch panel nodes quickly:

```python
from patching import make_patch_panel

node_metadata = {}
node_metadata.update(make_patch_panel("R1", "PP-A", ["01", "02", "03"]))
```

Create a panel with fixed U-height metadata:

```python
from patching import make_patch_panel_with_u_height

node_metadata.update(make_patch_panel_with_u_height("R1", "PP-Z", ["01", "02"], u_height=12, status="spare"))
```

Port status values are:

- `spare`
- `connected` (for example connected to endpoint `client1:LAN A`)
- `patched` (patch-cord chained to another panel/port)

## Route APIs

All routing APIs are in `patching.py`.

### 1) Auto route

```python
from patching import route_auto

result = route_auto(graph, source, target)
```

Response shape:

```python
{
    "mode": "auto",
    "path": ["...", "..."],
    "total_cost": 6.0,
    "reachable": True
}
```

### 2) Manual route (waypoints)

```python
from patching import route_manual

result = route_manual(graph, source, target, waypoints=["room:aisle-3/tray:T17"])
```

- Solves each leg: source -> waypoint1 -> ... -> target
- Concatenates leg paths into one final path
- If any leg is unreachable, returns `reachable=False` and `failed_leg`

### 3) Route with selection filters

```python
from patching import route_with_selection

selection = {
    "allowed_panels": ["PP-A", "PP-B"],
    "allowed_racks": ["R1", "R2"],
    "blocked_ports": ["rack:R1/panel:PP-A/port:03"],
    "reserved_edges": ["nodeX->nodeY"],
    "u_height_range": [1, 47],
    "allowed_statuses": ["spare", "connected"],
    "allowed_fixed_cables": ["KX0001"]
}

result = route_with_selection(
    graph=graph,
    node_metadata=node_metadata,
    source=source,
    target=target,
    selection=selection,
    waypoints=[]
)
```

`route_with_selection` internally:

1. Filters graph by selection constraints
2. Runs manual routing if waypoints exist, otherwise auto routing
3. Returns `filtered_graph` in the result for visibility

Routing policy notes:

- Fixed cables are directional by default.
- In auto mode, `patched` ports are excluded from traversal.
- Manual mode can still force specific chained traversal using explicit waypoints.

## Fixed Cables (KX####)

Use fixed cables to model inter-rack links:

```python
from patching import make_fixed_cable, apply_fixed_cables

fixed_cables = {
    "KX0001": make_fixed_cable(
        cable_id="KX0001",
        from_node="rack:R1/panel:PP-A/port:24",
        to_node="rack:R2/panel:PP-B/port:24",
        weight=0.5
    )
}

graph_with_cables = apply_fixed_cables(graph, fixed_cables)
```

Generate cable IDs safely:

```python
from patching import build_cable_id

build_cable_id(1)   # KX0001
build_cable_id(42)  # KX0042
```

Manual routing can include a cable ID waypoint:

```python
from patching import route_manual

result = route_manual(
    graph_with_cables,
    source,
    target,
    waypoints=["KX0001"],
    fixed_cables=fixed_cables,
)
```

## JSON Interoperability

JSON cannot represent Python infinity directly.
This project uses `"INF"` as the explicit token.

Helpers:

- `encode_for_json(value)`
- `decode_from_json(value)`
- `to_json(payload)`
- `from_json(payload_json)`

Example:

```python
from patching import to_json, from_json

payload = {
    "path": [],
    "reachable": False,
    "total_cost": float("inf")
}

json_payload = to_json(payload)
# total_cost becomes "INF"

roundtrip = from_json(json_payload)
# total_cost becomes float("inf") again
```

## Minimal End-to-End Example

```python
from patching import (
    make_patch_panel,
    route_with_selection,
)

# node_metadata maps the node IDs to semantics like rack/panel/port/status
node_metadata = {}
node_metadata.update(make_patch_panel("R1", "PP-A", ["01"]))
node_metadata.update(make_patch_panel("R2", "PP-B", ["24"]))

src = "rack:R1/panel:PP-A/port:01"
dst = "rack:R2/panel:PP-B/port:24"
r1_path = "rack:R1/path:vertical-left"
tray = "room:aisle-3/tray:T17"
r2_path = "rack:R2/path:vertical-right"

node_metadata[r1_path] = {"type": "path_point", "rack": "R1"}
node_metadata[tray] = {"type": "path_point", "rack": None}
node_metadata[r2_path] = {"type": "path_point", "rack": "R2"}

graph = {
    src: {r1_path: 1.0},
    r1_path: {src: 1.0, tray: 2.0},
    tray: {r1_path: 2.0, r2_path: 2.0},
    r2_path: {tray: 2.0, dst: 1.0},
    dst: {r2_path: 1.0}
}

selection = {
    "allowed_racks": ["R1", "R2"]
}

result = route_with_selection(
    graph=graph,
    node_metadata=node_metadata,
    source=src,
    target=dst,
    selection=selection,
    waypoints=[tray]  # remove or [] for auto mode
)

print(result)
```

## Validation and Errors

`validate_graph(graph)` checks:

- Graph is a dict
- Node IDs are strings
- Neighbor maps are dicts
- Edge weights are numeric and non-negative

Additional validation now checks:

- Port `u_height` is in `1..47` when provided
- Port status is one of `spare|connected|patched`
- Fixed cable IDs match `KX####`

Routing raises `KeyError` when required nodes are missing from graph.

## Running Tests

From the project folder:

```bash
python3 tests.py
```

Current tests cover:

- Auto route correctness
- Manual waypoint routing correctness
- Selection filter behavior
- `"INF"` JSON roundtrip behavior
- U-height metadata behavior
- Directional fixed cable behavior
- Patched-port auto-route blocking policy
- Manual cable-ID waypoint handling
