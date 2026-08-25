"""Supabase-backed repository.

Day-2 implementation. Assumes Ganva's schema exists with tables:
    users(user_id text pk, taste_vector jsonb/vector, budget int, dietary jsonb,
          spice_pref int, last_updated timestamptz)
    interactions(user_id text, dish_id text, action text, ts timestamptz)

Enable by setting STORAGE_BACKEND=supabase and providing SUPABASE_URL + SUPABASE_KEY.
"""
from __future__ import annotations

from datetime import datetime

from supabase import Client, create_client

from ..config import SUPABASE_KEY, SUPABASE_URL
from ..models import Interaction, UserTaste


class SupabaseRepository:
    USERS_TABLE = "users"
    INTERACTIONS_TABLE = "interactions"

    def __init__(self, client: Client | None = None) -> None:
        if client is not None:
            self.client = client
        else:
            if not SUPABASE_URL or not SUPABASE_KEY:
                raise RuntimeError(
                    "SupabaseRepository needs SUPABASE_URL and SUPABASE_KEY in the environment."
                )
            self.client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # --- users ---
    def upsert_user(self, user: UserTaste) -> None:
        row = {
            "user_id": user.user_id,
            "taste_vector": user.taste_vector,
            "budget": user.budget,
            "dietary": user.dietary,
            "spice_pref": user.spice_pref,
            "last_updated": user.last_updated.isoformat(),
        }
        self.client.table(self.USERS_TABLE).upsert(row).execute()

    def get_user(self, user_id: str) -> UserTaste | None:
        resp = self.client.table(self.USERS_TABLE).select("*").eq("user_id", user_id).limit(1).execute()
        rows = resp.data or []
        if not rows:
            return None
        return UserTaste.model_validate(self._decode(rows[0]))

    def all_users(self) -> list[UserTaste]:
        resp = self.client.table(self.USERS_TABLE).select("*").execute()
        return [UserTaste.model_validate(self._decode(r)) for r in (resp.data or [])]

    # --- interactions ---
    def add_interaction(self, interaction: Interaction) -> None:
        row = {
            "user_id": interaction.user_id,
            "dish_id": interaction.dish_id,
            "action": interaction.action,
            "ts": interaction.ts.isoformat(),
        }
        self.client.table(self.INTERACTIONS_TABLE).insert(row).execute()

    def interactions_for_user(self, user_id: str) -> list[Interaction]:
        resp = self.client.table(self.INTERACTIONS_TABLE).select("*").eq("user_id", user_id).execute()
        return [Interaction.model_validate(r) for r in (resp.data or [])]

    def all_interactions(self) -> list[Interaction]:
        resp = self.client.table(self.INTERACTIONS_TABLE).select("*").execute()
        return [Interaction.model_validate(r) for r in (resp.data or [])]

    @staticmethod
    def _decode(row: dict) -> dict:
        # Supabase returns timestamps as ISO strings and vectors as lists already;
        # accept datetime objects too if the underlying driver ever hands them back.
        ts = row.get("last_updated")
        if isinstance(ts, datetime):
            row["last_updated"] = ts.isoformat()
        return row
