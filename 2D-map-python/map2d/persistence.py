from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from .models import EditorData


class ValidationError(ValueError):
    pass


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def validate_project_payload(payload: Any) -> None:
    if not _is_record(payload):
        raise ValidationError("Project data must be an object.")

    required = ("version", "rooms", "objects", "cables", "activeRoomId")
    for key in required:
        if key not in payload:
            raise ValidationError(f"Missing field: {key}")

    if payload["version"] != 1:
        raise ValidationError("Unsupported project version. Expected version 1.")

    if not isinstance(payload["rooms"], list):
        raise ValidationError("rooms must be an array.")
    if not isinstance(payload["objects"], list):
        raise ValidationError("objects must be an array.")
    if not isinstance(payload["cables"], list):
        raise ValidationError("cables must be an array.")
    if payload["activeRoomId"] is not None and not isinstance(payload["activeRoomId"], str):
        raise ValidationError("activeRoomId must be a string or null.")


def export_project_json(data: EditorData) -> str:
    return json.dumps(data.to_dict(), indent=2)


def parse_project_json(content: str) -> EditorData:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValidationError(f"Invalid JSON: {error.msg}") from error
    validate_project_payload(payload)
    return EditorData.from_dict(payload)


def save_project_file(path: Path, data: EditorData) -> None:
    path.write_text(export_project_json(data), encoding="utf-8")


def load_project_file(path: Path) -> EditorData:
    return parse_project_json(path.read_text(encoding="utf-8"))


class DraftStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / ".cable-routing-2d-map")
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "draft.json"

    def save(self, data: EditorData) -> None:
        save_project_file(self.path, data)

    def load(self) -> EditorData | None:
        if not self.path.exists():
            return None
        try:
            return load_project_file(self.path)
        except (ValidationError, OSError):
            return None

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
