"""User taste-vector + interaction API — the surface Esha's ranking engine calls."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..context import context_signal
from ..dish_store import dish_vector
from ..models import ContextSignal, Interaction, InteractionAction, SimilarUser, UserTaste
from ..personalization import apply_interaction_update
from ..repositories import get_repository
from ..vector_math import top_k_similar
from pydantic import BaseModel

router = APIRouter(prefix="/api/user", tags=["user"])


class InteractionIn(BaseModel):
    dish_id: str
    action: InteractionAction


class InteractionAck(BaseModel):
    ok: bool
    user_id: str
    dish_id: str
    action: InteractionAction
    vector_updated: bool


@router.get("/{user_id}/taste-vector", response_model=UserTaste)
def get_taste_vector(user_id: str) -> UserTaste:
    user = get_repository().get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    return user


@router.get("/{user_id}/interaction", response_model=list[Interaction])
def list_interactions(user_id: str) -> list[Interaction]:
    return get_repository().interactions_for_user(user_id)


@router.post("/{user_id}/interaction", response_model=InteractionAck)
def log_interaction(user_id: str, payload: InteractionIn) -> InteractionAck:
    repo = get_repository()
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")

    interaction = Interaction(user_id=user_id, dish_id=payload.dish_id, action=payload.action)
    repo.add_interaction(interaction)

    dv = dish_vector(payload.dish_id)
    vector_updated = False
    if dv is not None:
        updated = apply_interaction_update(user, dv)
        repo.upsert_user(updated)
        vector_updated = True

    return InteractionAck(
        ok=True,
        user_id=user_id,
        dish_id=payload.dish_id,
        action=payload.action,
        vector_updated=vector_updated,
    )


@router.get("/{user_id}/similar", response_model=list[SimilarUser])
def similar_users(user_id: str, k: int = 5) -> list[SimilarUser]:
    repo = get_repository()
    me = repo.get_user(user_id)
    if not me:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    others = {u.user_id: u.taste_vector for u in repo.all_users() if u.user_id != user_id}
    ranked = top_k_similar(me.taste_vector, others, k=k)
    return [SimilarUser(user_id=uid, score=score) for uid, score in ranked]


@router.get("/{user_id}/context", response_model=ContextSignal)
def get_context(user_id: str) -> ContextSignal:
    repo = get_repository()
    user = repo.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    interactions = repo.interactions_for_user(user_id)
    signal = context_signal(interactions)
    return ContextSignal(user_id=user_id, **signal)
