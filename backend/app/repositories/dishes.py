import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.dish import Dish
from app.repositories.base import BaseRepository


class DishRepository(BaseRepository[Dish]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Dish)

    def get(self, item_id: object) -> Dish | None:
        return self.session.scalar(
            select(Dish).options(joinedload(Dish.restaurant)).where(Dish.id == item_id)
        )

    def list(
        self,
        *,
        restaurant_id: uuid.UUID | None,
        cuisine: str | None,
        name: str | None,
        min_price: Decimal | None,
        max_price: Decimal | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Dish], int]:
        query = select(Dish).options(joinedload(Dish.restaurant)).order_by(Dish.name, Dish.id)
        if restaurant_id:
            query = query.where(Dish.restaurant_id == restaurant_id)
        if cuisine:
            query = query.where(func.lower(Dish.cuisine) == cuisine.lower())
        if name:
            query = query.where(func.lower(Dish.name).contains(name.lower()))
        if min_price is not None:
            query = query.where(Dish.price >= min_price)
        if max_price is not None:
            query = query.where(Dish.price <= max_price)
        return self.page(query, limit=limit, offset=offset)
