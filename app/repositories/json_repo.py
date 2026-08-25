"""JSON-file repository. Day-1 stand-in for Supabase.

Each collection is one file under data/. Reads and writes are atomic on
individual operations; concurrent writers are not supported (dev-only).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from ..config import DATA_DIR
from ..models import Interaction, UserTaste


class JsonRepository:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.users_path = self.data_dir / "users.json"
        self.interactions_path = self.data_dir / "interactions.json"
        self._lock = threading.Lock()
        for p in (self.users_path, self.interactions_path):
            if not p.exists():
                p.write_text("[]", encoding="utf-8")

    def _read(self, path: Path) -> list[dict]:
        return json.loads(path.read_text(encoding="utf-8") or "[]")

    def _write(self, path: Path, rows: list[dict]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
        tmp.replace(path)

    def upsert_user(self, user: UserTaste) -> None:
        with self._lock:
            rows = self._read(self.users_path)
            payload = json.loads(user.model_dump_json())
            rows = [r for r in rows if r.get("user_id") != user.user_id]
            rows.append(payload)
            self._write(self.users_path, rows)

    def get_user(self, user_id: str) -> UserTaste | None:
        for r in self._read(self.users_path):
            if r.get("user_id") == user_id:
                return UserTaste.model_validate(r)
        return None

    def all_users(self) -> list[UserTaste]:
        return [UserTaste.model_validate(r) for r in self._read(self.users_path)]

    def add_interaction(self, interaction: Interaction) -> None:
        with self._lock:
            rows = self._read(self.interactions_path)
            rows.append(json.loads(interaction.model_dump_json()))
            self._write(self.interactions_path, rows)

    def interactions_for_user(self, user_id: str) -> list[Interaction]:
        return [
            Interaction.model_validate(r)
            for r in self._read(self.interactions_path)
            if r.get("user_id") == user_id
        ]

    def all_interactions(self) -> list[Interaction]:
        return [Interaction.model_validate(r) for r in self._read(self.interactions_path)]
