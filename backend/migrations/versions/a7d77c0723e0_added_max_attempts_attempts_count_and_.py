"""Add retry limits, attempt counts, and availability timestamps.

Preserve existing attempt numbers without granting additional retry attempts.

Revision ID: a7d77c0723e0
Revises: 43dcc043466c
Create Date: 2026-11-12 11:49:44.901575

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d77c0723e0"
down_revision: str | Sequence[str] | None = "43dcc043466c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Keep jobs and their attempts stable while reconstructing the counters.
    op.execute("LOCK TABLE jobs, job_attempts IN ACCESS EXCLUSIVE MODE")
    op.add_column("jobs", sa.Column("max_attempts", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("attempts_count", sa.Integer(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
    )
    op.execute("""
        UPDATE jobs
        SET attempts_count = COALESCE(
            (SELECT MAX(attempt_number)
             FROM job_attempts
             WHERE job_attempts.job_id = jobs.id),
            0
        )
    """)
    op.execute("UPDATE jobs SET max_attempts = GREATEST(1, attempts_count)")
    op.alter_column("jobs", "max_attempts", nullable=False)
    op.alter_column("jobs", "attempts_count", nullable=False)
    op.create_check_constraint(
        "ck_jobs_positive_max_attempts", "jobs", "max_attempts > 0"
    )
    op.create_check_constraint(
        "ck_jobs_attempts_count_within_limit",
        "jobs",
        "attempts_count >= 0 AND attempts_count <= max_attempts",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_jobs_attempts_count_within_limit", "jobs", type_="check")
    op.drop_constraint("ck_jobs_positive_max_attempts", "jobs", type_="check")
    op.drop_column("jobs", "available_at")
    op.drop_column("jobs", "attempts_count")
    op.drop_column("jobs", "max_attempts")
