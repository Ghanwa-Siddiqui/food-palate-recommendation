"""Repository interface.

Any concrete backend (JSON on disk, Supabase Postgres, etc.) implements this
so the rest of the app never touches storage details directly.
"""
from __future__ import annotations

from typing import Protocol

from ..models import Interaction, UserTaste


class Repository(Protocol):
    # --- users ---
    def upsert_user(self, user: UserTaste) -> None: ...

    def get_user(self, user_id: str) -> UserTaste | None: ...

    def all_users(self) -> list[UserTaste]: ...

    # --- interactions ---
    def add_interaction(self, interaction: Interaction) -> None: ...

    def interactions_for_user(self, user_id: str) -> list[Interaction]: ...

    def all_interactions(self) -> list[Interaction]: ...
