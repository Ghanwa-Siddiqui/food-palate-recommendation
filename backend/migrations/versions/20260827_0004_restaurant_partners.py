"""Add restaurant-partner roles and restaurant ownership fields."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260827_0004"
down_revision = "20260827_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(30), nullable=False, server_default="customer"),
    )
    op.create_check_constraint(
        "user_role_values",
        "users",
        "role IN ('customer', 'restaurant_partner', 'admin')",
    )
    op.add_column(
        "restaurants",
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("restaurants", sa.Column("contact_phone", sa.String(40), nullable=True))
    op.add_column(
        "restaurants",
        sa.Column(
            "halal_verification_status",
            sa.String(30),
            nullable=False,
            server_default="unverified",
        ),
    )
    op.add_column("restaurants", sa.Column("opening_information", sa.String(500), nullable=True))
    op.add_column(
        "restaurants",
        sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("restaurants", sa.Column("image_path", sa.String(300), nullable=True))
    op.create_foreign_key(
        "fk_restaurants_owner_id_users",
        "restaurants",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_restaurants_owner_id", "restaurants", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_restaurants_owner_id", table_name="restaurants")
    op.drop_constraint("fk_restaurants_owner_id_users", "restaurants", type_="foreignkey")
    for column in (
        "image_path",
        "available",
        "opening_information",
        "halal_verification_status",
        "contact_phone",
        "owner_id",
    ):
        op.drop_column("restaurants", column)
    op.drop_constraint("user_role_values", "users", type_="check")
    op.drop_column("users", "role")
