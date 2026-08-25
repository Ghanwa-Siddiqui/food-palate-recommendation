"""Allow sourced restaurants to have unverified coordinates."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0002"
down_revision = "20260825_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("restaurants", "latitude", existing_type=sa.Numeric(9, 6), nullable=True)
    op.alter_column("restaurants", "longitude", existing_type=sa.Numeric(9, 6), nullable=True)
    op.add_column(
        "restaurants",
        sa.Column("location_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("restaurants", sa.Column("coordinates_source_url", sa.String(1000)))
    op.add_column("restaurants", sa.Column("coordinates_verified_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "coordinate_pair",
        "restaurants",
        "(latitude IS NULL) = (longitude IS NULL)",
    )
    op.create_check_constraint(
        "verified_coordinates_present",
        "restaurants",
        "NOT location_verified OR (latitude IS NOT NULL AND longitude IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("verified_coordinates_present", "restaurants", type_="check")
    op.drop_constraint("coordinate_pair", "restaurants", type_="check")
    op.drop_column("restaurants", "coordinates_verified_at")
    op.drop_column("restaurants", "coordinates_source_url")
    op.drop_column("restaurants", "location_verified")
    op.alter_column("restaurants", "longitude", existing_type=sa.Numeric(9, 6), nullable=False)
    op.alter_column("restaurants", "latitude", existing_type=sa.Numeric(9, 6), nullable=False)
