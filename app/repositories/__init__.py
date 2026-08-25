"""Storage layer. Choose backend via STORAGE_BACKEND env var."""
from __future__ import annotations

from ..config import STORAGE_BACKEND
from .base import Repository
from .json_repo import JsonRepository


def get_repository() -> Repository:
    if STORAGE_BACKEND == "supabase":
        from .supabase_repo import SupabaseRepository
        return SupabaseRepository()
    return JsonRepository()


__all__ = ["Repository", "get_repository"]
