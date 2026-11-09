"""Add submission idempotency fields, preserving existing jobs.

Legacy jobs receive synthetic keys and a non-replayable fingerprint marker.

Revision ID: 4610066358ca
Revises: 476550d0c277
Create Date: 2026-11-09 17:45:51.748590

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4610066358ca"
down_revision: str | Sequence[str] | None = "476550d0c277"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "jobs", sa.Column("idempotency_key", sa.String(length=100), nullable=True)
    )
    op.add_column(
        "jobs", sa.Column("request_fingerprint", sa.String(length=100), nullable=True)
    )
    # Original submission keys and fingerprints were never stored.
    op.execute("""
        UPDATE jobs
        SET idempotency_key = 'legacy-job:' || id::text,
            request_fingerprint = 'legacy'
    """)
    op.alter_column("jobs", "idempotency_key", nullable=False)
    op.alter_column("jobs", "request_fingerprint", nullable=False)
    op.create_unique_constraint(
        "uq_idempotency_key_user_id", "jobs", ["user_id", "idempotency_key"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_idempotency_key_user_id", "jobs", type_="unique")
    op.drop_column("jobs", "request_fingerprint")
    op.drop_column("jobs", "idempotency_key")
