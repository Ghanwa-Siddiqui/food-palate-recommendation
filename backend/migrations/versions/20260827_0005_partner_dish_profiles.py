"""Add partner-managed dish profile lifecycle metadata."""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0005"
down_revision = "20260827_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dishes", sa.Column("embedding_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("dishes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dishes", sa.Column("image_path", sa.String(300), nullable=True))
    op.add_column("dishes", sa.Column("creation_key", sa.String(64), nullable=True))
    op.create_index("ix_dishes_archived_at", "dishes", ["archived_at"])
    op.create_unique_constraint("uq_dishes_creation_key", "dishes", ["creation_key"])


def downgrade() -> None:
    op.drop_constraint("uq_dishes_creation_key", "dishes", type_="unique")
    op.drop_index("ix_dishes_archived_at", table_name="dishes")
    for column in ("creation_key", "image_path", "archived_at", "embedding_updated_at"):
        op.drop_column("dishes", column)
