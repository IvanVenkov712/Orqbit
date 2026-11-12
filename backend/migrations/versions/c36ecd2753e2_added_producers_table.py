"""added producers table

Revision ID: c36ecd2753e2
Revises: a7d77c0723e0
Create Date: 2026-11-12 19:43:14.194116

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c36ecd2753e2"
down_revision: str | Sequence[str] | None = "a7d77c0723e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "producers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("secret_api_key_hash", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("secret_api_key_hash"),
    )
    op.add_column("jobs", sa.Column("producer_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_producer_id", "jobs", "producers", ["producer_id"], ["id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_jobs_producer_id", "jobs", type_="foreignkey")
    op.drop_column("jobs", "producer_id")
    op.drop_table("producers")
