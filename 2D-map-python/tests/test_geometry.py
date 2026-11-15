import unittest

from map2d.geometry import cable_length_meters
from map2d.models import CableModel, RoomPoint


class GeometryTests(unittest.TestCase):
    def test_dynamic_length_uses_route(self) -> None:
        cable = CableModel(
            id="c1",
            label="",
            tag="",
            comment="",
            type="network",
            diameter_mm=10.0,
            color="#777777",
            points=[
                RoomPoint(0.0, 0.0, "room-1"),
                RoomPoint(3.0, 4.0, "room-1"),
            ],
            bend_radius_meters=[],
            length_mode="dynamic",
            fixed_length_meters=None,
        )
        self.assertEqual(cable_length_meters(cable), 5.0)

    def test_fixed_length_preferred(self) -> None:
        cable = CableModel(
            id="c2",
            label="",
            tag="",
            comment="",
            type="network",
            diameter_mm=10.0,
            color="#777777",
            points=[
                RoomPoint(0.0, 0.0, "room-1"),
                RoomPoint(3.0, 4.0, "room-1"),
            ],
            bend_radius_meters=[],
            length_mode="fixed",
            fixed_length_meters=12.5,
        )
        self.assertEqual(cable_length_meters(cable), 12.5)


if __name__ == "__main__":
    unittest.main()
