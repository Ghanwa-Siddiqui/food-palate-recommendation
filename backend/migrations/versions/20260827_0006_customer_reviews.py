"""Add customer review workflow, intelligence aggregates, and interaction evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0006"
down_revision = "20260827_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "show_review_display_name", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.drop_constraint("action_values", "interactions", type_="check")
    op.create_check_constraint(
        "action_values",
        "interactions",
        "action IN ('click','save','order','tried','like','dislike')",
    )
    op.add_column(
        "reviews",
        sa.Column("processing_status", sa.String(30), server_default="pending", nullable=False),
    )
    op.add_column("reviews", sa.Column("processing_error_code", sa.String(60)))
    op.add_column("reviews", sa.Column("submission_key", sa.String(64)))
    op.execute(
        "UPDATE reviews SET submission_key = 'legacy-' || id::text WHERE submission_key IS NULL"
    )
    op.alter_column("reviews", "submission_key", nullable=False)
    op.create_unique_constraint("uq_reviews_submission_key", "reviews", ["submission_key"])
    op.add_column(
        "reviews",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column("reviews", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.create_index("ix_reviews_archived_at", "reviews", ["archived_at"])
    op.create_index(
        "uq_reviews_active_user_dish",
        "reviews",
        ["user_id", "dish_id"],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )
    for column in (
        sa.Column("review_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_average", sa.Numeric(3, 2)),
        sa.Column("review_sentiment", sa.Numeric(5, 4)),
        sa.Column("review_spice", sa.Numeric(5, 3)),
        sa.Column("review_oiliness", sa.Numeric(5, 3)),
        sa.Column("review_flavor_tags", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("review_aggregated_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("dishes", column)


def downgrade() -> None:
    for name in (
        "review_aggregated_at",
        "review_flavor_tags",
        "review_oiliness",
        "review_spice",
        "review_sentiment",
        "review_average",
        "review_count",
    ):
        op.drop_column("dishes", name)
    op.drop_index("uq_reviews_active_user_dish", table_name="reviews")
    op.drop_index("ix_reviews_archived_at", table_name="reviews")
    for name in ("archived_at", "updated_at"):
        op.drop_column("reviews", name)
    op.drop_constraint("uq_reviews_submission_key", "reviews", type_="unique")
    for name in ("submission_key", "processing_error_code", "processing_status"):
        op.drop_column("reviews", name)
    op.drop_constraint("action_values", "interactions", type_="check")
    op.create_check_constraint(
        "action_values", "interactions", "action IN ('click','save','order')"
    )
    op.drop_column("users", "show_review_display_name")
