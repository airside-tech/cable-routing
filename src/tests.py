import unittest

from patching import (
    INF_TOKEN,
    build_cable_id,
    decode_from_json,
    encode_for_json,
    filter_graph_by_selection,
    from_json,
    make_fixed_cable,
    make_patch_panel,
    make_patch_panel_with_u_height,
    route_auto,
    route_manual,
    route_with_selection,
    to_json,
    apply_fixed_cables,
)


class RoutingTests(unittest.TestCase):

    def setUp(self):
        self.node_metadata = {}
        self.node_metadata.update(make_patch_panel("R1", "PP-A", ["01"]))
        self.node_metadata.update(make_patch_panel("R2", "PP-B", ["24"]))

        self.src = "rack:R1/panel:PP-A/port:01"
        self.dst = "rack:R2/panel:PP-B/port:24"
        self.r1_path = "rack:R1/path:vertical-left"
        self.tray = "room:aisle-3/tray:T17"
        self.r2_path = "rack:R2/path:vertical-right"

        self.node_metadata[self.r1_path] = {"type": "path_point", "rack": "R1"}
        self.node_metadata[self.tray] = {"type": "path_point", "rack": None}
        self.node_metadata[self.r2_path] = {"type": "path_point", "rack": "R2"}

        # Directed graph with reverse edges where physically reachable in both directions.
        self.graph = {
            self.src: {self.r1_path: 1.0},
            self.r1_path: {self.src: 1.0, self.tray: 2.0},
            self.tray: {self.r1_path: 2.0, self.r2_path: 2.0},
            self.r2_path: {self.tray: 2.0, self.dst: 1.0},
            self.dst: {self.r2_path: 1.0}
        }

    def test_auto_route(self):
        result = route_auto(self.graph, self.src, self.dst)
        self.assertTrue(result["reachable"])
        self.assertEqual(result["path"], [self.src, self.r1_path, self.tray, self.r2_path, self.dst])
        self.assertEqual(result["total_cost"], 6.0)

    def test_manual_route_with_waypoint(self):
        result = route_manual(self.graph, self.src, self.dst, [self.tray])
        self.assertTrue(result["reachable"])
        self.assertIn(self.tray, result["path"])
        self.assertEqual(result["path"][0], self.src)
        self.assertEqual(result["path"][-1], self.dst)

    def test_selection_blocks_route(self):
        selection = {
            "blocked_ports": [self.r2_path]
        }
        filtered = filter_graph_by_selection(self.graph, self.node_metadata, selection, self.src, self.dst)
        result = route_auto(filtered, self.src, self.dst)
        self.assertFalse(result["reachable"])

    def test_route_with_selection_wrapper(self):
        selection = {"allowed_racks": ["R1", "R2"]}
        result = route_with_selection(self.graph, self.node_metadata, self.src, self.dst, selection)
        self.assertTrue(result["reachable"])
        self.assertIn("filtered_graph", result)

    def test_inf_json_roundtrip(self):
        payload = {
            "cost": float("inf"),
            "path": [],
            "reachable": False
        }
        encoded = encode_for_json(payload)
        self.assertEqual(encoded["cost"], INF_TOKEN)

        json_payload = to_json(payload)
        decoded = from_json(json_payload)
        self.assertEqual(decoded["cost"], float("inf"))

    def test_decode_from_json_inf_token(self):
        decoded = decode_from_json({"distance": INF_TOKEN})
        self.assertEqual(decoded["distance"], float("inf"))

    def test_make_patch_panel_with_u_height(self):
        nodes = make_patch_panel_with_u_height("R1", "PP-C", ["01", "02"], 12, status="spare")
        node = nodes["rack:R1/panel:PP-C/port:01"]
        self.assertEqual(node["u_height"], 12)
        self.assertEqual(node["status"], "spare")

    def test_build_cable_id(self):
        self.assertEqual(build_cable_id(1), "KX0001")
        self.assertEqual(build_cable_id(42), "KX0042")

    def test_apply_fixed_cables_directional(self):
        cable = make_fixed_cable("KX0001", self.r1_path, self.r2_path, weight=0.5)
        graph = apply_fixed_cables(self.graph, {"KX0001": cable})
        self.assertEqual(graph[self.r1_path][self.r2_path], 0.5)
        self.assertFalse(self.r1_path in graph[self.r2_path])

    def test_auto_mode_blocks_patched_ports(self):
        patched_mid = "rack:R2/panel:PP-B/port:99"
        self.node_metadata[patched_mid] = {
            "type": "patch_port",
            "rack": "R2",
            "panel": "PP-B",
            "port": "99",
            "u_height": 20,
            "status": "patched",
            "connected_endpoint": None,
            "patched_to": self.dst,
        }
        graph = {
            self.src: {patched_mid: 1.0},
            patched_mid: {self.dst: 1.0},
            self.dst: {}
        }

        result = route_with_selection(graph, self.node_metadata, self.src, self.dst, selection={})
        self.assertFalse(result["reachable"])

    def test_manual_mode_allows_explicit_cable_waypoint(self):
        cable = make_fixed_cable("KX0001", self.r1_path, self.r2_path, weight=0.5)
        graph_with_cable = apply_fixed_cables(self.graph, {"KX0001": cable})

        result = route_manual(
            graph_with_cable,
            self.src,
            self.dst,
            waypoints=["KX0001"],
            fixed_cables={"KX0001": cable}
        )
        self.assertTrue(result["reachable"])
        self.assertIn(self.r1_path, result["path"])
        self.assertIn(self.r2_path, result["path"])

    def test_selection_u_height_range_filters_nodes(self):
        high_port = "rack:R1/panel:PP-A/port:47"
        self.node_metadata[high_port] = {
            "type": "patch_port",
            "rack": "R1",
            "panel": "PP-A",
            "port": "47",
            "u_height": 47,
            "status": "spare",
            "connected_endpoint": None,
            "patched_to": None,
        }
        graph = {
            self.src: {high_port: 1.0},
            high_port: {self.dst: 1.0},
            self.dst: {}
        }

        filtered = filter_graph_by_selection(
            graph,
            self.node_metadata,
            selection={"u_height_range": [1, 20]},
            source=self.src,
            target=self.dst,
        )
        self.assertFalse(high_port in filtered)


if __name__ == "__main__":
    unittest.main()



