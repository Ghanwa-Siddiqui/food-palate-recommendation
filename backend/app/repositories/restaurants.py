from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.models.restaurant import Restaurant
from app.repositories.base import BaseRepository


class RestaurantRepository(BaseRepository[Restaurant]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Restaurant)

    def list(
        self,
        *,
        city: str | None,
        cuisine: str | None,
        halal_status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Restaurant], int]:
        query = select(Restaurant).order_by(Restaurant.name, Restaurant.id)
        if city:
            query = query.where(func.lower(Restaurant.city) == city.lower())
        if cuisine:
            dialect = self.session.get_bind().dialect.name
            if dialect == "postgresql":
                values = func.json_array_elements_text(Restaurant.cuisine_types).table_valued(
                    "value"
                )
            elif dialect == "sqlite":
                values = func.json_each(Restaurant.cuisine_types).table_valued("key", "value")
            else:
                raise RuntimeError(f"unsupported JSON cuisine-filter dialect: {dialect}")
            query = query.where(
                exists(
                    select(1)
                    .select_from(values)
                    .where(func.lower(values.c.value) == cuisine.casefold())
                )
            )
        if halal_status:
            query = query.where(func.lower(Restaurant.halal_status) == halal_status.lower())
        return self.page(query, limit=limit, offset=offset)
