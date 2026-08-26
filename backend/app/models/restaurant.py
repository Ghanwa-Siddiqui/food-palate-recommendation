from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Restaurant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "restaurants"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="coordinate_pair"),
        CheckConstraint(
            "NOT location_verified OR (latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="verified_coordinates_present",
        ),
        CheckConstraint(
            "halal_status IN ('verified', 'claimed', 'not_halal', 'unknown')",
            name="halal_status_values",
        ),
    )

    name: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    cuisine_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    address: Mapped[str] = mapped_column(String(300), nullable=False)
    city: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    location_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    coordinates_source_url: Mapped[str | None] = mapped_column(String(1000))
    coordinates_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_range: Mapped[str] = mapped_column(String(20), nullable=False)
    halal_status: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    dishes = relationship("Dish", back_populates="restaurant", cascade="all, delete-orphan")
    deals = relationship("Deal", back_populates="restaurant", cascade="all, delete-orphan")
