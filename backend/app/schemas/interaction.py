import uuid
from datetime import datetime
from typing import Literal

from app.schemas.common import ORMModel


class InteractionRead(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    dish_id: uuid.UUID
    action: Literal["click", "save", "order"]
    ts: datetime
