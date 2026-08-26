import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.deal import Deal
from app.repositories.base import BaseRepository


class DealRepository(BaseRepository[Deal]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Deal)

    def list(
        self,
        *,
        restaurant_id: uuid.UUID | None,
        active_only: bool,
        now: datetime,
        limit: int,
        offset: int,
    ) -> tuple[list[Deal], int]:
        query = select(Deal).order_by(Deal.starts_at.desc(), Deal.id)
        if restaurant_id:
            query = query.where(Deal.restaurant_id == restaurant_id)
        if active_only:
            query = query.where(Deal.is_active.is_(True), Deal.starts_at <= now, Deal.ends_at > now)
        return self.page(query, limit=limit, offset=offset)
