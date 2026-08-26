from typing import Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def get(self, item_id: object) -> ModelT | None:
        return self.session.get(self.model, item_id)

    def page(self, statement: Select, *, limit: int, offset: int) -> tuple[list[ModelT], int]:
        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(self.session.scalars(statement.limit(limit).offset(offset)))
        return items, total
