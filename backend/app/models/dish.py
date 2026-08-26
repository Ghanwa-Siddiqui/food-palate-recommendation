import uuid
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIMENSION
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Dish(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dishes"
    __table_args__ = (
        CheckConstraint("price >= 0", name="price_nonnegative"),
        CheckConstraint("spice_level BETWEEN 0 AND 5", name="spice_level_range"),
        CheckConstraint("oiliness BETWEEN 0 AND 5", name="oiliness_range"),
        CheckConstraint("sweetness BETWEEN 0 AND 5", name="sweetness_range"),
        CheckConstraint("sourness BETWEEN 0 AND 5", name="sourness_range"),
        CheckConstraint("saltiness BETWEEN 0 AND 5", name="saltiness_range"),
        CheckConstraint("smokiness BETWEEN 0 AND 5", name="smokiness_range"),
        CheckConstraint("richness BETWEEN 0 AND 5", name="richness_range"),
    )

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("restaurants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(180), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cuisine: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    ingredients: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    spice_level: Mapped[int] = mapped_column(Integer, nullable=False)
    oiliness: Mapped[int] = mapped_column(Integer, nullable=False)
    sweetness: Mapped[int] = mapped_column(Integer, nullable=False)
    sourness: Mapped[int] = mapped_column(Integer, nullable=False)
    saltiness: Mapped[int] = mapped_column(Integer, nullable=False)
    smokiness: Mapped[int] = mapped_column(Integer, nullable=False)
    richness: Mapped[int] = mapped_column(Integer, nullable=False)
    texture_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    dietary_tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allergens: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    preparation_style: Mapped[str] = mapped_column(String(100), nullable=False)
    availability: Mapped[bool] = mapped_column(default=True, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    restaurant = relationship("Restaurant", back_populates="dishes")
    reviews = relationship("Review", back_populates="dish", cascade="all, delete-orphan")
    interactions = relationship("Interaction", back_populates="dish", cascade="all, delete-orphan")
