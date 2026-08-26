import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class ReviewRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    dish_id: uuid.UUID
    rating: int = Field(ge=1, le=5)
    text: str | None
    created_at: datetime
