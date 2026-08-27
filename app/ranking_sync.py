"""Best-effort mirror of newly onboarded users into the local dev ranking
backend's SQLite DB, so /app/feed works immediately after onboarding without
a manual DB insert.

This is a demo/dev convenience only. The ranking backend (Ganva/Esha's
`backend/`) owns its own `users` table and is a separate service in
production — this module never imports their code, just writes a plain SQL
row via stdlib sqlite3, and silently no-ops if their local dev DB isn't
present or anything goes wrong. Onboarding must never fail because of this.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import ROOT_DIR

_RANKING_DB_PATH = ROOT_DIR / "backend" / "dev_ranking.db"


def mirror_demo_user(user_id: str, name: str = "Namak Demo User") -> None:
    if not _RANKING_DB_PATH.exists():
        return
    try:
        # SQLAlchemy's sa.Uuid() column stores values as a 32-char hex string
        # with no dashes on SQLite (verified empirically) — a dashed insert
        # silently never matches session.get(User, uuid.UUID(...)) lookups.
        stored_id = user_id.replace("-", "")
        email = f"{stored_id}@demo.local"
        conn = sqlite3.connect(str(_RANKING_DB_PATH), timeout=2)
        try:
            # Delete-then-insert rather than INSERT OR IGNORE: the `email`
            # column has its own unique constraint separate from the `id`
            # primary key, so a stale row (e.g. from an earlier bad id
            # format) can silently block a fresh insert keyed only on id.
            conn.execute("DELETE FROM users WHERE id = ? OR email = ?", (stored_id, email))
            conn.execute(
                "INSERT INTO users (id, name, email, created_at, updated_at) "
                "VALUES (?, ?, ?, datetime('now'), datetime('now'))",
                (stored_id, name, email),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass
