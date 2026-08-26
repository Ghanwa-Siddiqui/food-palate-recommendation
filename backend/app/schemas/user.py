import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import ORMModel


class UserRead(ORMModel):
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    created_at: datetime
    updated_at: datetime
