import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIMENSION
from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class Review(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint("sentiment BETWEEN -1 AND 1", name="review_sentiment_range"),
        CheckConstraint("spice_score BETWEEN 0 AND 5", name="review_spice_range"),
        CheckConstraint("oiliness_score BETWEEN 0 AND 5", name="review_oiliness_range"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), index=True)
    dish_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("dishes.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[float | None] = mapped_column(Float)
    spice_score: Mapped[float | None] = mapped_column(Float)
    oiliness_score: Mapped[float | None] = mapped_column(Float)
    flavor_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    review_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    processing_status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    processing_error_code: Mapped[str | None] = mapped_column(String(60))
    submission_key: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=lambda: uuid.uuid4().hex
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user = relationship("User", back_populates="reviews")
    dish = relationship("Dish", back_populates="reviews")
