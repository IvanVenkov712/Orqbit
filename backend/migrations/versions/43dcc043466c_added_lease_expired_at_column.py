"""Add lease_expires_at, preserving terminal attempts.

Terminal attempts use updated_at as a synthetic deadline. Resolve RUNNING
attempts before upgrading; their original lease deadlines cannot be reconstructed.

Revision ID: 43dcc043466c
Revises: 4610066358ca
Create Date: 2026-11-11 16:47:57.357428

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "43dcc043466c"
down_revision: str | Sequence[str] | None = "4610066358ca"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Prevent attempts changing between the RUNNING check and the backfill.
    op.execute("LOCK TABLE job_attempts IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM job_attempts WHERE status = 'RUNNING') THEN
                RAISE EXCEPTION 'Resolve legacy RUNNING attempts before upgrading';
            END IF;
        END $$;
    """)
    op.add_column(
        "job_attempts",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # No real lease deadline was recorded for these historical attempts.
    op.execute("UPDATE job_attempts SET lease_expires_at = updated_at")
    op.alter_column("job_attempts", "lease_expires_at", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_attempts", "lease_expires_at")
