import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    # First allow empty values for existing jobs.
    op.add_column(
        "jobs",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Fill existing rows.
    op.execute(
        sa.text("""
            UPDATE jobs
            SET created_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
        """)
    )

    # Now every row has values, so require them.
    op.alter_column("jobs", "created_at", nullable=False)
    op.alter_column("jobs", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("jobs", "updated_at")
    op.drop_column("jobs", "created_at")