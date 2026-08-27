import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.api.dependencies import PrivateAPIDependency, SessionDependency
from app.models.restaurant import Restaurant
from app.models.user import User
from app.schemas.restaurant import (
    PartnerRestaurantCreate,
    PartnerRestaurantUpdate,
    RestaurantRead,
)

router = APIRouter(prefix="/partner/restaurants", tags=["restaurant-partner"])


def _actor(
    session: SessionDependency,
    actor_id: str | None,
) -> User:
    try:
        user_id = uuid.UUID(actor_id or "")
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Partner access required") from exc
    user = session.get(User, user_id)
    if user is None or user.role not in {"restaurant_partner", "admin"}:
        raise HTTPException(status_code=403, detail="Partner access required")
    return user


@router.get("", response_model=list[RestaurantRead])
def list_owned_restaurants(
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user = _actor(session, actor)
    query = select(Restaurant).order_by(Restaurant.name, Restaurant.id)
    if user.role != "admin":
        query = query.where(Restaurant.owner_id == user.id)
    return list(session.scalars(query))


@router.post("", response_model=RestaurantRead, status_code=201)
def create_restaurant(
    payload: PartnerRestaurantCreate,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user = _actor(session, actor)
    values = payload.model_dump(exclude={"lat", "lng"})
    item = Restaurant(
        **values,
        owner_id=user.id,
        latitude=payload.lat,
        longitude=payload.lng,
        location_verified=False,
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.put("/{restaurant_id}", response_model=RestaurantRead)
def update_restaurant(
    restaurant_id: uuid.UUID,
    payload: PartnerRestaurantUpdate,
    session: SessionDependency,
    _private: PrivateAPIDependency,
    actor: Annotated[str | None, Header(alias="X-Chaska-User-ID")] = None,
):
    user = _actor(session, actor)
    item = session.get(Restaurant, restaurant_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    if user.role != "admin" and item.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Restaurant ownership check failed")
    for field, value in payload.model_dump(exclude={"lat", "lng"}).items():
        setattr(item, field, value)
    item.latitude = payload.lat
    item.longitude = payload.lng
    item.location_verified = False
    session.commit()
    session.refresh(item)
    return item
