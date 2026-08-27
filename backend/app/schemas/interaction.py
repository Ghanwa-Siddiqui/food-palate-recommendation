import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class InteractionRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    dish_id: uuid.UUID
    action: Literal["click", "save", "order", "tried", "like", "dislike"]
    ts: datetime
    client_event_id: str | None = None


class InteractionCreate(BaseModel):
    dish_id: uuid.UUID
    action: Literal["click", "save", "order", "tried", "like", "dislike"]
    client_event_id: str = Field(min_length=8, max_length=64)


class InteractionResult(InteractionRead):
    duplicate: bool = False
