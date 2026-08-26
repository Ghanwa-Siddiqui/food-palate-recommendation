import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models.dish import Dish
from app.repositories.deals import DealRepository
from app.repositories.dishes import DishRepository
from app.repositories.restaurants import RestaurantRepository
from app.schemas.deal import DealPage, DealRead
from app.schemas.dish import DishPage, DishRead, DishVectorRead
from app.schemas.restaurant import RestaurantPage, RestaurantRead


class NotFoundError(Exception):
    def __init__(self, resource: str, resource_id: object) -> None:
        self.resource = resource
        self.resource_id = resource_id
        super().__init__(f"{resource} {resource_id} was not found")


class InvalidRequestError(ValueError):
    pass


class EmbeddingUnavailableError(Exception):
    def __init__(self, dish_id: object) -> None:
        self.dish_id = dish_id
        super().__init__(f"dish {dish_id} exists but has no embedding")


def _dish_read(dish: Dish) -> DishRead:
    return DishRead.model_validate(
        {
            **dish.__dict__,
            "lat": dish.restaurant.latitude if dish.restaurant else None,
            "lng": dish.restaurant.longitude if dish.restaurant else None,
        }
    )


class RestaurantService:
    def __init__(self, repository: RestaurantRepository) -> None:
        self.repository = repository

    def list(self, **filters) -> RestaurantPage:
        items, total = self.repository.list(**filters)
        return RestaurantPage(
            items=items, total=total, limit=filters["limit"], offset=filters["offset"]
        )

    def get(self, restaurant_id: uuid.UUID) -> RestaurantRead:
        item = self.repository.get(restaurant_id)
        if item is None:
            raise NotFoundError("restaurant", restaurant_id)
        return RestaurantRead.model_validate(item)


class DishService:
    def __init__(self, repository: DishRepository) -> None:
        self.repository = repository

    def list(self, **filters) -> DishPage:
        min_price: Decimal | None = filters.get("min_price")
        max_price: Decimal | None = filters.get("max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise InvalidRequestError("min_price cannot exceed max_price")
        items, total = self.repository.list(**filters)
        return DishPage(
            items=[_dish_read(item) for item in items],
            total=total,
            limit=filters["limit"],
            offset=filters["offset"],
        )

    def get(self, dish_id: uuid.UUID) -> DishRead:
        item = self.repository.get(dish_id)
        if item is None:
            raise NotFoundError("dish", dish_id)
        return _dish_read(item)

    def vector(self, dish_id: uuid.UUID) -> DishVectorRead:
        item = self.repository.get(dish_id)
        if item is None:
            raise NotFoundError("dish", dish_id)
        if item.embedding is None:
            raise EmbeddingUnavailableError(dish_id)
        return DishVectorRead(id=item.id, vector=[float(value) for value in item.embedding])


class DealService:
    def __init__(self, repository: DealRepository) -> None:
        self.repository = repository

    def list(self, **filters) -> DealPage:
        filters.setdefault("now", datetime.now(UTC))
        items, total = self.repository.list(**filters)
        return DealPage(
            items=[DealRead.model_validate(item) for item in items],
            total=total,
            limit=filters["limit"],
            offset=filters["offset"],
        )

    def get(self, deal_id: uuid.UUID) -> DealRead:
        item = self.repository.get(deal_id)
        if item is None:
            raise NotFoundError("deal", deal_id)
        return DealRead.model_validate(item)
