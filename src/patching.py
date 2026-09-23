'''
Model each patch port as a node.
Model each internal rack path segment as a node or edge.
Model each physical cable-able connection as a weighted edge.
Keep panel selection as a filter over allowed nodes/edges, not a separate algorithm.

1. Define a JSON request/response contract.
2. Represent patch panels, ports, and rack path points as graph node IDs plus metadata.
3. Keep a single graph format for both modes: node -> neighbor -> weight.
4. Add two routing modes over that graph:
5. Auto mode: shortest path from source to target.
6. Manual mode: shortest path leg-by-leg across ordered waypoints.
7. Refactor dijkstra_v2 entry flow so solving is callable (not constructor-driven).
8. Add schema validation and structured errors for malformed inputs and unreachable paths.
9. Add JSON interoperability tests, including INF roundtrip and waypoint ordering.

'''

import json
import re
from dijkstra_v2 import Graph_v2

infinity = float("inf")
INF_TOKEN = "INF"
PORT_STATUS_VALUES = {"spare", "connected", "patched"}
CABLE_ID_PATTERN = re.compile(r"^KX\d{4}$")


def make_port_node_id(rack: str, panel: str, port: str):
	return f"rack:{rack}/panel:{panel}/port:{port}"


def make_path_node_id(rack: str, path_name: str):
	return f"rack:{rack}/path:{path_name}"


def make_patch_panel(rack: str, panel: str, ports: list):
	nodes = {}
	for port in ports:
		node_id = make_port_node_id(rack, panel, str(port))
		nodes[node_id] = {
			"type": "patch_port",
			"rack": rack,
			"panel": panel,
			"port": str(port),
			"u_height": None,
			"status": "spare",
			"connected_endpoint": None,
			"patched_to": None
		}
	return nodes


def make_patch_panel_with_u_height(rack: str, panel: str, ports: list, u_height: int, status: str = "spare"):
	if not isinstance(u_height, int) or u_height < 1 or u_height > 47:
		raise ValueError("u_height must be an integer in range 1..47")
	if status not in PORT_STATUS_VALUES:
		raise ValueError(f"status must be one of {sorted(PORT_STATUS_VALUES)}")

	nodes = {}
	for port in ports:
		node_id = make_port_node_id(rack, panel, str(port))
		nodes[node_id] = {
			"type": "patch_port",
			"rack": rack,
			"panel": panel,
			"port": str(port),
			"u_height": u_height,
			"status": status,
			"connected_endpoint": None,
			"patched_to": None
		}

	return nodes


def validate_cable_id(cable_id: str):
	if not isinstance(cable_id, str) or not CABLE_ID_PATTERN.match(cable_id):
		raise ValueError("cable_id must match format KX####, for example KX0001")


def build_cable_id(number: int):
	if not isinstance(number, int) or number < 1 or number > 9999:
		raise ValueError("cable number must be an integer in range 1..9999")
	return f"KX{number:04d}"


def make_fixed_cable(cable_id: str, from_node: str, to_node: str, weight: float = 1.0, status: str = "installed"):
	validate_cable_id(cable_id)
	if not isinstance(from_node, str) or not isinstance(to_node, str):
		raise TypeError("from_node and to_node must be strings")
	if not isinstance(weight, (int, float)) or weight < 0:
		raise ValueError("weight must be a non-negative number")

	return {
		"id": cable_id,
		"from_node": from_node,
		"to_node": to_node,
		"weight": float(weight),
		"status": status,
		"directional": True
	}


def validate_node_metadata(node_metadata: dict):
	if not isinstance(node_metadata, dict):
		raise TypeError("node_metadata must be a dict")

	for node_id, meta in node_metadata.items():
		if not isinstance(node_id, str):
			raise TypeError("all node_metadata keys must be strings")
		if not isinstance(meta, dict):
			raise TypeError(f"metadata for node '{node_id}' must be a dict")

		if meta.get("type") == "patch_port":
			status = meta.get("status")
			if status is not None and status not in PORT_STATUS_VALUES:
				raise ValueError(f"invalid port status '{status}' for node '{node_id}'")

			u_height = meta.get("u_height")
			if u_height is not None:
				if not isinstance(u_height, int) or u_height < 1 or u_height > 47:
					raise ValueError(f"u_height for node '{node_id}' must be an integer in range 1..47")


def validate_fixed_cables(fixed_cables: dict):
	if fixed_cables is None:
		return
	if not isinstance(fixed_cables, dict):
		raise TypeError("fixed_cables must be a dict keyed by cable_id")

	for cable_id, cable in fixed_cables.items():
		validate_cable_id(cable_id)
		if not isinstance(cable, dict):
			raise TypeError(f"fixed_cables['{cable_id}'] must be a dict")

		if cable.get("id") is not None and cable.get("id") != cable_id:
			raise ValueError(f"fixed cable id mismatch for '{cable_id}'")

		if "from_node" not in cable or "to_node" not in cable:
			raise ValueError(f"fixed cable '{cable_id}' must define from_node and to_node")

		weight = cable.get("weight", 1.0)
		if not isinstance(weight, (int, float)) or weight < 0:
			raise ValueError(f"fixed cable '{cable_id}' weight must be a non-negative number")


def validate_graph(graph: dict):
	if not isinstance(graph, dict):
		raise TypeError("graph must be a dict")

	for node, neighbors in graph.items():
		if not isinstance(node, str):
			raise TypeError("all graph node IDs must be strings")
		if not isinstance(neighbors, dict):
			raise TypeError(f"neighbors for node '{node}' must be a dict")

		for neighbor, weight in neighbors.items():
			if not isinstance(neighbor, str):
				raise TypeError("all neighbor node IDs must be strings")
			if not isinstance(weight, (int, float)):
				raise TypeError(f"edge weight from '{node}' to '{neighbor}' must be numeric")
			if weight < 0:
				raise ValueError(f"edge weight from '{node}' to '{neighbor}' cannot be negative")


def encode_for_json(value):
	if isinstance(value, float) and value == infinity:
		return INF_TOKEN

	if isinstance(value, dict):
		return {k: encode_for_json(v) for k, v in value.items()}

	if isinstance(value, list):
		return [encode_for_json(v) for v in value]

	return value


def decode_from_json(value):
	if value == INF_TOKEN:
		return infinity

	if isinstance(value, dict):
		return {k: decode_from_json(v) for k, v in value.items()}

	if isinstance(value, list):
		return [decode_from_json(v) for v in value]

	return value


def to_json(payload: dict):
	return json.dumps(encode_for_json(payload), indent=2)


def from_json(payload_json: str):
	return decode_from_json(json.loads(payload_json))


def fixed_cable_edge_map(fixed_cables: dict):
	edge_to_cable = {}
	if not fixed_cables:
		return edge_to_cable

	validate_fixed_cables(fixed_cables)
	for cable_id, cable in fixed_cables.items():
		if cable.get("status", "installed") != "installed":
			continue
		edge_id = f"{cable['from_node']}->{cable['to_node']}"
		edge_to_cable[edge_id] = cable_id

	return edge_to_cable


def apply_fixed_cables(graph: dict, fixed_cables: dict):
	validate_graph(graph)
	validate_fixed_cables(fixed_cables)

	new_graph = {node: dict(neighbors) for node, neighbors in graph.items()}
	for cable_id, cable in fixed_cables.items():
		if cable.get("status", "installed") != "installed":
			continue

		from_node = cable["from_node"]
		to_node = cable["to_node"]
		weight = float(cable.get("weight", 1.0))

		if from_node not in new_graph:
			new_graph[from_node] = {}
		if to_node not in new_graph:
			new_graph[to_node] = {}

		# Fixed cables are directional by policy.
		new_graph[from_node][to_node] = weight

	return new_graph


def filter_graph_by_selection(graph: dict, node_metadata: dict, selection: dict, source: str = None, target: str = None, fixed_cables: dict = None, mode: str = "auto"):
	validate_node_metadata(node_metadata)
	validate_fixed_cables(fixed_cables)

	allowed_panels = set(selection.get("allowed_panels", []))
	allowed_racks = set(selection.get("allowed_racks", []))
	blocked_ports = set(selection.get("blocked_ports", []))
	reserved_edges = set(selection.get("reserved_edges", []))
	allowed_statuses = set(selection.get("allowed_statuses", []))
	u_height_range = selection.get("u_height_range")
	allowed_fixed_cables = set(selection.get("allowed_fixed_cables", []))
	fixed_edge_lookup = fixed_cable_edge_map(fixed_cables)

	if allowed_statuses:
		invalid_statuses = allowed_statuses - PORT_STATUS_VALUES
		if invalid_statuses:
			raise ValueError(f"invalid statuses in allowed_statuses: {sorted(invalid_statuses)}")

	min_u = None
	max_u = None
	if u_height_range is not None:
		if not isinstance(u_height_range, (list, tuple)) or len(u_height_range) != 2:
			raise ValueError("u_height_range must be a 2-item list/tuple like [1, 47]")
		min_u, max_u = u_height_range
		if not isinstance(min_u, int) or not isinstance(max_u, int):
			raise ValueError("u_height_range values must be integers")
		if min_u < 1 or max_u > 47 or min_u > max_u:
			raise ValueError("u_height_range must satisfy 1 <= min <= max <= 47")

	if allowed_fixed_cables:
		for cable_id in allowed_fixed_cables:
			validate_cable_id(cable_id)

	forced_nodes = {n for n in [source, target] if n is not None}

	def node_allowed(node_id: str):
		if node_id in forced_nodes:
			return True
		if node_id in blocked_ports:
			return False

		meta = node_metadata.get(node_id, {})
		panel = meta.get("panel")
		rack = meta.get("rack")
		status = meta.get("status")
		node_type = meta.get("type")
		u_height = meta.get("u_height")

		if allowed_panels and panel is not None and panel not in allowed_panels:
			return False
		if allowed_racks and rack is not None and rack not in allowed_racks:
			return False
		if allowed_statuses and status is not None and status not in allowed_statuses:
			return False
		if min_u is not None and u_height is not None and (u_height < min_u or u_height > max_u):
			return False

		# Policy decision: patched ports cannot be traversed by auto-routing.
		if mode == "auto" and node_type == "patch_port" and status == "patched":
			return False

		return True

	filtered = {}
	for node, neighbors in graph.items():
		if not node_allowed(node):
			continue

		filtered_neighbors = {}
		for neighbor, weight in neighbors.items():
			if not node_allowed(neighbor):
				continue
			edge_id = f"{node}->{neighbor}"
			if edge_id in reserved_edges:
				continue

			if allowed_fixed_cables:
				cable_id = fixed_edge_lookup.get(edge_id)
				if cable_id is not None and cable_id not in allowed_fixed_cables:
					continue

			filtered_neighbors[neighbor] = weight

		filtered[node] = filtered_neighbors

	return filtered


def path_cost(graph: dict, path: list):
	if not path:
		return infinity

	total = 0.0
	for idx in range(len(path) - 1):
		src = path[idx]
		dst = path[idx + 1]
		if src not in graph or dst not in graph[src]:
			return infinity
		total += graph[src][dst]
	return total


def route_auto(graph: dict, source: str, target: str):
	validate_graph(graph)

	if source not in graph:
		raise KeyError(f"source node '{source}' not found")
	if target not in graph:
		raise KeyError(f"target node '{target}' not found")

	dijkstra = Graph_v2(graph, auto_solve=False)
	path = dijkstra.shortest_path(source, target)
	total_cost = dijkstra.costs.get(target, infinity)

	return {
		"mode": "auto",
		"path": path,
		"total_cost": total_cost,
		"reachable": total_cost != infinity
	}


def expand_waypoints(waypoints: list, fixed_cables: dict = None):
	waypoints = waypoints or []
	if not fixed_cables:
		return list(waypoints)

	validate_fixed_cables(fixed_cables)
	expanded = []
	for waypoint in waypoints:
		if isinstance(waypoint, str) and CABLE_ID_PATTERN.match(waypoint):
			if waypoint not in fixed_cables:
				raise KeyError(f"fixed cable waypoint '{waypoint}' not found")
			cable = fixed_cables[waypoint]
			expanded.extend([cable["from_node"], cable["to_node"]])
		else:
			expanded.append(waypoint)

	return expanded


def route_manual(graph: dict, source: str, target: str, waypoints: list, fixed_cables: dict = None):
	validate_graph(graph)
	waypoints = expand_waypoints(waypoints, fixed_cables)

	for node in [source, target] + list(waypoints):
		if node not in graph:
			raise KeyError(f"node '{node}' not found in graph")

	route_nodes = [source]
	for waypoint in list(waypoints) + [target]:
		if route_nodes[-1] != waypoint:
			route_nodes.append(waypoint)
	full_path = []
	total_cost = 0.0

	dijkstra = Graph_v2(graph, auto_solve=False)

	for idx in range(len(route_nodes) - 1):
		leg_source = route_nodes[idx]
		leg_target = route_nodes[idx + 1]
		leg_path = dijkstra.shortest_path(leg_source, leg_target)
		leg_cost = dijkstra.costs.get(leg_target, infinity)

		if leg_cost == infinity or not leg_path:
			return {
				"mode": "manual",
				"path": [],
				"total_cost": infinity,
				"reachable": False,
				"failed_leg": {
					"source": leg_source,
					"target": leg_target
				}
			}

		if not full_path:
			full_path.extend(leg_path)
		else:
			full_path.extend(leg_path[1:])
		total_cost += leg_cost

	return {
		"mode": "manual",
		"path": full_path,
		"total_cost": total_cost,
		"reachable": True
	}


def route_with_selection(graph: dict, node_metadata: dict, source: str, target: str, selection: dict = None, waypoints: list = None, fixed_cables: dict = None):
	selection = selection or {}
	graph_with_cables = apply_fixed_cables(graph, fixed_cables) if fixed_cables else graph
	routing_mode = "manual" if waypoints else "auto"
	filtered_graph = filter_graph_by_selection(
		graph_with_cables,
		node_metadata,
		selection,
		source,
		target,
		fixed_cables=fixed_cables,
		mode=routing_mode
	)

	if waypoints:
		result = route_manual(filtered_graph, source, target, waypoints, fixed_cables=fixed_cables)
	else:
		result = route_auto(filtered_graph, source, target)

	result["filtered_graph"] = filtered_graph
	return result


