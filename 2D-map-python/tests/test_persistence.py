from pathlib import Path
import tempfile
import unittest

from map2d.models import create_initial_data, create_room, generate_default_room_name
from map2d.persistence import DraftStore, ValidationError, parse_project_json


class PersistenceTests(unittest.TestCase):
    def test_parse_validation_rejects_missing_fields(self) -> None:
        with self.assertRaises(ValidationError):
            parse_project_json('{"version": 1}')

    def test_round_trip_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DraftStore(Path(tmp))
            data = create_initial_data()
            store.save(data)

            loaded = store.load()
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.version, 1)
            self.assertEqual(len(loaded.rooms), 1)
            self.assertEqual(loaded.active_room_id, data.active_room_id)

    def test_room_names_and_metadata_roundtrip(self) -> None:
        room_a = create_room("Room A", 8, 6, building="North Wing", floor="3")
        room_b = create_room("Room B", 6, 4)
        self.assertEqual(generate_default_room_name([room_a, room_b]), "Room C")

        payload = room_a.to_dict()
        restored = type(room_a).from_dict(payload)
        self.assertEqual(restored.building, "North Wing")
        self.assertEqual(restored.floor, "3")
        self.assertEqual(restored.name, "Room A")


if __name__ == "__main__":
    unittest.main()
