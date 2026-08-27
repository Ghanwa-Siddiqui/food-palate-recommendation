import math
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy import delete, select

from app.api.dependencies import PrivateAPIDependency, SessionDependency
from app.core.config import get_settings
from app.models.dish import Dish
from app.models.interaction import Interaction
from app.models.user import User
from app.schemas.interaction import InteractionCreate, InteractionRead, InteractionResult
from app.schemas.user import (
    SimilarUserRead,
    TasteProfileRead,
    TasteProfileUpdate,
    UserRead,
    UserSync,
)
from app.services.data_core.catalog import NotFoundError

router = APIRouter(prefix="/users", tags=["users"])


def _authorize(user_id: uuid.UUID, actor: str | None) -> None:
    if get_settings().internal_api_key and actor != str(user_id):
        raise HTTPException(status_code=403, detail="User ownership check failed")


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    magnitude = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
    return dot / magnitude if magnitude else 0.0


@router.post("/sync", response_model=UserRead)
def sync_user(payload: UserSync, session: SessionDependency, _private: PrivateAPIDependency):
    user = session.get(User, payload.id)
    if user is None:
        user = User(
            id=payload.id,
            name=payload.name,
            email=payload.email.casefold(),
            role=payload.role or "customer",
        )
        session.add(user)
    else:
        user.name = payload.name
        user.email = payload.email.casefold()
    session.commit()
    session.refresh(user)
    return user


@router.get("/{user_id}/profile", response_model=TasteProfileRead)
def get_profile(
    user_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    _authorize(user_id, actor)
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user", user_id)
    return user


@router.put("/{user_id}/profile", response_model=TasteProfileRead)
def update_profile(
    user_id: uuid.UUID,
    payload: TasteProfileUpdate,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    _authorize(user_id, actor)
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user", user_id)
    for field, value in payload.model_dump(exclude={"taste_vector"}).items():
        setattr(user, field, value)
    user.taste_vector = payload.taste_vector
    user.taste_updated_at = datetime.now(UTC)
    user.onboarding_complete = True
    session.commit()
    session.refresh(user)
    return user


@router.get("/{user_id}/interactions", response_model=list[InteractionRead])
def list_interactions(
    user_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    _authorize(user_id, actor)
    return list(
        session.scalars(
            select(Interaction)
            .where(Interaction.user_id == user_id)
            .order_by(Interaction.ts.desc(), Interaction.id.desc())
        )
    )


@router.post("/{user_id}/interactions", response_model=InteractionResult)
def add_interaction(
    user_id: uuid.UUID,
    payload: InteractionCreate,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    _authorize(user_id, actor)
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user", user_id)
    dish = session.get(Dish, payload.dish_id)
    if dish is None:
        raise NotFoundError("dish", payload.dish_id)
    existing = session.scalar(
        select(Interaction).where(Interaction.client_event_id == payload.client_event_id)
    )
    if existing is not None:
        if existing.user_id != user_id:
            raise HTTPException(status_code=409, detail="Interaction key already used")
        return InteractionResult.model_validate(existing).model_copy(update={"duplicate": True})
    if payload.action in {"save", "tried", "like", "dislike"}:
        saved = session.scalar(
            select(Interaction).where(
                Interaction.user_id == user_id,
                Interaction.dish_id == payload.dish_id,
                Interaction.action == payload.action,
            )
        )
        if saved is not None:
            return InteractionResult.model_validate(saved).model_copy(update={"duplicate": True})

    interaction = Interaction(
        user_id=user_id,
        dish_id=payload.dish_id,
        action=payload.action,
        client_event_id=payload.client_event_id,
    )
    session.add(interaction)
    if (
        payload.action not in {"tried", "dislike"}
        and user.taste_vector is not None
        and dish.embedding is not None
    ):
        alpha = 0.15
        blended = [
            (1 - alpha) * old + alpha * new
            for old, new in zip(user.taste_vector, dish.embedding, strict=True)
        ]
        norm = math.sqrt(sum(value * value for value in blended))
        user.taste_vector = [value / norm for value in blended] if norm else blended
        user.taste_updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(interaction)
    return InteractionResult.model_validate(interaction)


@router.delete("/{user_id}/saved/{dish_id}", status_code=204)
def unsave_dish(
    user_id: uuid.UUID,
    dish_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    _authorize(user_id, actor)
    session.execute(
        delete(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.dish_id == dish_id,
            Interaction.action == "save",
        )
    )
    session.commit()
    return Response(status_code=204)


@router.get("/{user_id}/similar", response_model=list[SimilarUserRead])
def similar_users(
    user_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
    limit: int = 5,
):
    _authorize(user_id, actor)
    user = session.get(User, user_id)
    if user is None:
        raise NotFoundError("user", user_id)
    if user.taste_vector is None:
        return []
    others = session.scalars(
        select(User).where(User.id != user_id, User.taste_vector.is_not(None)).limit(100)
    )
    ranked = sorted(
        (
            SimilarUserRead(
                user_id=other.id,
                name=other.name,
                score=_cosine(user.taste_vector, other.taste_vector),
            )
            for other in others
        ),
        key=lambda item: (-item.score, str(item.user_id)),
    )
    return ranked[: max(1, min(limit, 20))]
