import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class Interaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "interactions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('click', 'save', 'order', 'tried', 'like', 'dislike')", name="action_values"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    dish_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("dishes.id"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    client_event_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user = relationship("User", back_populates="interactions")
    dish = relationship("Dish", back_populates="interactions")
