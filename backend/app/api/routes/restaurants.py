import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.dependencies import SessionDependency
from app.repositories.dishes import DishRepository
from app.repositories.restaurants import RestaurantRepository
from app.schemas.dish import DishPage
from app.schemas.restaurant import HalalStatus, RestaurantPage, RestaurantRead
from app.services.data_core.catalog import DishService, RestaurantService

router = APIRouter(prefix="/restaurants", tags=["restaurants"])


@router.get("", response_model=RestaurantPage)
def list_restaurants(
    session: SessionDependency,
    city: str | None = None,
    cuisine: str | None = None,
    halal_status: HalalStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RestaurantPage:
    return RestaurantService(RestaurantRepository(session)).list(
        city=city,
        cuisine=cuisine,
        halal_status=halal_status,
        limit=limit,
        offset=offset,
    )


@router.get("/{restaurant_id}", response_model=RestaurantRead)
def get_restaurant(restaurant_id: uuid.UUID, session: SessionDependency) -> RestaurantRead:
    return RestaurantService(RestaurantRepository(session)).get(restaurant_id)


@router.get("/{restaurant_id}/dishes", response_model=DishPage)
def list_restaurant_dishes(
    restaurant_id: uuid.UUID,
    session: SessionDependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DishPage:
    RestaurantService(RestaurantRepository(session)).get(restaurant_id)
    return DishService(DishRepository(session)).list(
        restaurant_id=restaurant_id,
        cuisine=None,
        name=None,
        min_price=None,
        max_price=None,
        limit=limit,
        offset=offset,
    )
