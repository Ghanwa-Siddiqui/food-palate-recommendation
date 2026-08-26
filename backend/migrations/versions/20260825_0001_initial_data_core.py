"""Initial Data Layer and Backend Core tables."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.constants import EMBEDDING_DIMENSION

revision = "20260825_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "restaurants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("cuisine_types", sa.JSON(), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("price_range", sa.String(20), nullable=False),
        sa.Column("halal_status", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_restaurants"),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90",
            name=op.f("ck_restaurants_latitude_range"),
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name=op.f("ck_restaurants_longitude_range"),
        ),
        sa.CheckConstraint(
            "halal_status IN ('verified', 'claimed', 'not_halal', 'unknown')",
            name=op.f("ck_restaurants_halal_status_values"),
        ),
    )
    op.create_index("ix_restaurants_name", "restaurants", ["name"])
    op.create_index("ix_restaurants_city", "restaurants", ["city"])
    op.create_index("ix_restaurants_halal_status", "restaurants", ["halal_status"])
    op.create_table(
        "dishes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("cuisine", sa.String(100), nullable=False),
        sa.Column("ingredients", sa.JSON(), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("spice_level", sa.Integer(), nullable=False),
        sa.Column("oiliness", sa.Integer(), nullable=False),
        sa.Column("sweetness", sa.Integer(), nullable=False),
        sa.Column("sourness", sa.Integer(), nullable=False),
        sa.Column("saltiness", sa.Integer(), nullable=False),
        sa.Column("smokiness", sa.Integer(), nullable=False),
        sa.Column("richness", sa.Integer(), nullable=False),
        sa.Column("texture_tags", sa.JSON(), nullable=False),
        sa.Column("dietary_tags", sa.JSON(), nullable=False),
        sa.Column("allergens", sa.JSON(), nullable=False),
        sa.Column("preparation_style", sa.String(100), nullable=False),
        sa.Column("availability", sa.Boolean(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSION)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("price >= 0", name=op.f("ck_dishes_price_nonnegative")),
        sa.CheckConstraint("spice_level BETWEEN 0 AND 5", name=op.f("ck_dishes_spice_level_range")),
        sa.CheckConstraint("oiliness BETWEEN 0 AND 5", name=op.f("ck_dishes_oiliness_range")),
        sa.CheckConstraint("sweetness BETWEEN 0 AND 5", name=op.f("ck_dishes_sweetness_range")),
        sa.CheckConstraint("sourness BETWEEN 0 AND 5", name=op.f("ck_dishes_sourness_range")),
        sa.CheckConstraint("saltiness BETWEEN 0 AND 5", name=op.f("ck_dishes_saltiness_range")),
        sa.CheckConstraint("smokiness BETWEEN 0 AND 5", name=op.f("ck_dishes_smokiness_range")),
        sa.CheckConstraint("richness BETWEEN 0 AND 5", name=op.f("ck_dishes_richness_range")),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="CASCADE",
            name="fk_dishes_restaurant_id_restaurants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dishes"),
    )
    op.create_index("ix_dishes_restaurant_id", "dishes", ["restaurant_id"])
    op.create_index("ix_dishes_name", "dishes", ["name"])
    op.create_index("ix_dishes_cuisine", "dishes", ["cuisine"])
    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("restaurant_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("discount_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "discount_percentage BETWEEN 0 AND 100",
            name=op.f("ck_deals_discount_range"),
        ),
        sa.CheckConstraint("ends_at > starts_at", name=op.f("ck_deals_valid_date_range")),
        sa.ForeignKeyConstraint(
            ["restaurant_id"],
            ["restaurants.id"],
            ondelete="CASCADE",
            name="fk_deals_restaurant_id_restaurants",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_deals"),
    )
    op.create_index("ix_deals_restaurant_id", "deals", ["restaurant_id"])
    op.create_index("ix_deals_is_active", "deals", ["is_active"])
    op.create_table(
        "reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name=op.f("ck_reviews_rating_range")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_reviews_user_id_users"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_reviews_dish_id_dishes"),
        sa.PrimaryKeyConstraint("id", name="pk_reviews"),
    )
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])
    op.create_index("ix_reviews_dish_id", "reviews", ["dish_id"])
    op.create_table(
        "interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("dish_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_interactions_user_id_users"),
        sa.ForeignKeyConstraint(["dish_id"], ["dishes.id"], name="fk_interactions_dish_id_dishes"),
        sa.PrimaryKeyConstraint("id", name="pk_interactions"),
        sa.CheckConstraint(
            "action IN ('click', 'save', 'order')",
            name=op.f("ck_interactions_action_values"),
        ),
    )
    op.create_index("ix_interactions_user_id", "interactions", ["user_id"])
    op.create_index("ix_interactions_dish_id", "interactions", ["dish_id"])
    op.create_index("ix_interactions_action", "interactions", ["action"])


def downgrade() -> None:
    op.drop_table("interactions")
    op.drop_table("reviews")
    op.drop_table("deals")
    op.drop_table("dishes")
    op.drop_table("restaurants")
    op.drop_table("users")
    # The shared vector extension is intentionally retained.
