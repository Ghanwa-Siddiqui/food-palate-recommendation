import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select

from app.api.dependencies import PrivateAPIDependency, SessionDependency
from app.api.routes.partner_restaurants import _actor
from app.core.constants import EMBEDDING_DIMENSION
from app.models.dish import Dish
from app.models.restaurant import Restaurant
from app.schemas.dish import DishRead, PartnerDishCreate, PartnerDishUpdate
from app.services.data_core.dish_profiles import (
    DishEmbeddingService,
    get_dish_embedding_service,
)

router = APIRouter(prefix="/partner", tags=["restaurant-partner-menu"])
EmbeddingDependency = Annotated[DishEmbeddingService, Depends(get_dish_embedding_service)]


def _owned_restaurant(session, user, restaurant_id: uuid.UUID) -> Restaurant:
    restaurant = session.get(Restaurant, restaurant_id)
    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    if user.role != "admin" and restaurant.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Restaurant ownership check failed")
    return restaurant


def _owned_dish(session, user, dish_id: uuid.UUID) -> Dish:
    dish = session.get(Dish, dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    _owned_restaurant(session, user, dish.restaurant_id)
    return dish


def _embedding(service: DishEmbeddingService, payload) -> list[float]:
    vector = service.generate(payload)
    if len(vector) != EMBEDDING_DIMENSION:
        raise HTTPException(status_code=500, detail="Dish profile vector generation failed")
    return vector


@router.get("/restaurants/{restaurant_id}/dishes", response_model=list[DishRead])
def list_owned_menu(
    restaurant_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user = _actor(session, actor)
    _owned_restaurant(session, user, restaurant_id)
    return list(
        session.scalars(
            select(Dish)
            .where(Dish.restaurant_id == restaurant_id)
            .order_by(Dish.archived_at.nulls_first(), Dish.name, Dish.id)
        )
    )


@router.post("/dishes", response_model=DishRead, status_code=201)
def create_dish(
    payload: PartnerDishCreate,
    embedding_service: EmbeddingDependency,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
    creation_key: Annotated[str | None, Header(alias="X-Idempotency-Key")] = None,
):
    user = _actor(session, actor)
    _owned_restaurant(session, user, payload.restaurant_id)
    if not creation_key or not 16 <= len(creation_key) <= 64:
        raise HTTPException(status_code=422, detail="Valid idempotency key required")
    existing = session.scalar(select(Dish).where(Dish.creation_key == creation_key))
    if existing is not None:
        _owned_restaurant(session, user, existing.restaurant_id)
        return existing
    values = payload.model_dump(exclude={"restaurant_id"})
    now = datetime.now(UTC)
    dish = Dish(
        **values,
        restaurant_id=payload.restaurant_id,
        embedding=_embedding(embedding_service, payload),
        embedding_updated_at=now,
        creation_key=creation_key,
    )
    session.add(dish)
    session.commit()
    session.refresh(dish)
    return dish


@router.get("/dishes/{dish_id}", response_model=DishRead)
def get_owned_dish(
    dish_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    return _owned_dish(session, _actor(session, actor), dish_id)


@router.put("/dishes/{dish_id}", response_model=DishRead)
def update_dish(
    dish_id: uuid.UUID,
    payload: PartnerDishUpdate,
    embedding_service: EmbeddingDependency,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    dish = _owned_dish(session, _actor(session, actor), dish_id)
    for field, value in payload.model_dump().items():
        setattr(dish, field, value)
    dish.embedding = _embedding(embedding_service, payload)
    dish.embedding_updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(dish)
    return dish


@router.post("/dishes/{dish_id}/availability", response_model=DishRead)
def set_availability(
    dish_id: uuid.UUID,
    available: bool,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    dish = _owned_dish(session, _actor(session, actor), dish_id)
    if dish.archived_at is not None and available:
        raise HTTPException(status_code=409, detail="Archived dishes cannot be activated")
    dish.availability = available
    session.commit()
    session.refresh(dish)
    return dish


@router.post("/dishes/{dish_id}/archive", response_model=DishRead)
def archive_dish(
    dish_id: uuid.UUID,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    dish = _owned_dish(session, _actor(session, actor), dish_id)
    if dish.archived_at is None:
        dish.archived_at = datetime.now(UTC)
        dish.availability = False
        session.commit()
        session.refresh(dish)
    return dish
