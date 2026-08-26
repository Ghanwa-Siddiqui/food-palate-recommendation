import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency
from app.repositories.dishes import DishRepository
from app.schemas.dish import DishPage, DishRead, DishVectorRead
from app.services.data_core.catalog import DishService

router = APIRouter(prefix="/dishes", tags=["dishes"])


@router.get("", response_model=DishPage)
def list_dishes(
    session: SessionDependency,
    restaurant: uuid.UUID | None = None,
    cuisine: str | None = None,
    name: str | None = None,
    min_price: Annotated[Decimal | None, Query(ge=0)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DishPage:
    return DishService(DishRepository(session)).list(
        restaurant_id=restaurant,
        cuisine=cuisine,
        name=name,
        min_price=min_price,
        max_price=max_price,
        limit=limit,
        offset=offset,
    )


@router.get("/{dish_id}/vector", response_model=DishVectorRead)
def get_dish_vector(dish_id: uuid.UUID, session: SessionDependency) -> DishVectorRead:
    return DishService(DishRepository(session)).vector(dish_id)


@router.get("/{dish_id}", response_model=DishRead)
def get_dish(dish_id: uuid.UUID, session: SessionDependency) -> DishRead:
    return DishService(DishRepository(session)).get(dish_id)
