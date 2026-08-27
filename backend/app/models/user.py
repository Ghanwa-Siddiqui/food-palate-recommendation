from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import EMBEDDING_DIMENSION
from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('customer', 'restaurant_partner', 'admin')",
            name="user_role_values",
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="customer", nullable=False)
    onboarding_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    preferred_cuisines: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    favourite_dishes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    spice_preference: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    sweetness_preference: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    sourness_preference: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    saltiness_preference: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    oiliness_preference: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    richness_preference: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    preferred_textures: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    budget_min: Mapped[float] = mapped_column(Numeric(10, 2), default=0, nullable=False)
    budget_max: Mapped[float] = mapped_column(Numeric(10, 2), default=1500, nullable=False)
    dietary_requirements: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    allergies: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    disliked_ingredients: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    require_halal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_review_display_name: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taste_vector: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))
    taste_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviews = relationship("Review", back_populates="user", cascade="all, delete-orphan")
    interactions = relationship("Interaction", back_populates="user", cascade="all, delete-orphan")
    owned_restaurants = relationship("Restaurant", back_populates="owner")
