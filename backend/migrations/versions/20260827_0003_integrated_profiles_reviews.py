"""Add integrated taste profiles and structured review signals."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

from app.core.constants import EMBEDDING_DIMENSION

revision = "20260827_0003"
down_revision = "20260826_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    profile_columns = (
        sa.Column("onboarding_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("preferred_cuisines", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("favourite_dishes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("spice_preference", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("sweetness_preference", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("sourness_preference", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("saltiness_preference", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("oiliness_preference", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("richness_preference", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("preferred_textures", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("budget_min", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("budget_max", sa.Numeric(10, 2), nullable=False, server_default="1500"),
        sa.Column("dietary_requirements", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("allergies", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("disliked_ingredients", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("require_halal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("taste_vector", Vector(EMBEDDING_DIMENSION), nullable=True),
        sa.Column("taste_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in profile_columns:
        op.add_column("users", column)

    op.add_column("reviews", sa.Column("sentiment", sa.Float(), nullable=True))
    op.add_column("reviews", sa.Column("spice_score", sa.Float(), nullable=True))
    op.add_column("reviews", sa.Column("oiliness_score", sa.Float(), nullable=True))
    op.add_column(
        "reviews", sa.Column("flavor_tags", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column(
        "reviews", sa.Column("review_embedding", Vector(EMBEDDING_DIMENSION), nullable=True)
    )
    op.create_check_constraint("review_sentiment_range", "reviews", "sentiment BETWEEN -1 AND 1")
    op.create_check_constraint("review_spice_range", "reviews", "spice_score BETWEEN 0 AND 5")
    op.create_check_constraint("review_oiliness_range", "reviews", "oiliness_score BETWEEN 0 AND 5")

    op.add_column("interactions", sa.Column("client_event_id", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_interactions_client_event_id", "interactions", ["client_event_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_interactions_client_event_id", "interactions", type_="unique")
    op.drop_column("interactions", "client_event_id")
    for constraint in ("review_oiliness_range", "review_spice_range", "review_sentiment_range"):
        op.drop_constraint(constraint, "reviews", type_="check")
    for column in ("review_embedding", "flavor_tags", "oiliness_score", "spice_score", "sentiment"):
        op.drop_column("reviews", column)
    for column in (
        "taste_updated_at",
        "taste_vector",
        "require_halal",
        "disliked_ingredients",
        "allergies",
        "dietary_requirements",
        "budget_max",
        "budget_min",
        "preferred_textures",
        "richness_preference",
        "oiliness_preference",
        "saltiness_preference",
        "sourness_preference",
        "sweetness_preference",
        "spice_preference",
        "favourite_dishes",
        "preferred_cuisines",
        "city",
        "onboarding_complete",
    ):
        op.drop_column("users", column)
