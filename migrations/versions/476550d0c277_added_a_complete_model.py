"""Add users, workers, permissions, and job attempts.

Existing jobs become private and belong to an inactive legacy owner. Reassign
them explicitly before use. Resolve legacy RUNNING jobs before upgrading;
their worker and attempt ownership cannot be reconstructed.

Revision ID: 476550d0c277
Revises: 324192f7fa35
Create Date: 2026-11-08 22:47:17.372724

"""

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pwdlib import PasswordHash
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "476550d0c277"
down_revision: str | Sequence[str] | None = "324192f7fa35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Keep legacy rows stable until ownership and required columns are assigned.
    op.execute("LOCK TABLE jobs IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM jobs WHERE status = 'RUNNING') THEN
                RAISE EXCEPTION 'Resolve legacy RUNNING jobs before upgrading';
            END IF;
        END $$;
    """)
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("role", sa.Enum("ADMIN", "REGULAR", name="userrole"), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "workers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("secret_api_key_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "permission_policy",
            sa.Enum(
                "PRIVATE", "PERMITTED_USERS", "ALL", name="worker_permission_policy"
            ),
            nullable=False,
        ),
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
    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("RUNNING", "SUCCEEDED", "FAILED", "LOST", name="attemptstatus"),
            nullable=False,
        ),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_number > 0", name="ck_job_attempts_positive_number"
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number"),
    )
    op.create_index(
        "uq_job_attempts_one_running",
        "job_attempts",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.create_table(
        "job_permitted_users",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "job_id"),
    )
    op.create_table(
        "job_permitted_workers",
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.PrimaryKeyConstraint("worker_id", "job_id"),
    )
    op.create_table(
        "supported_job_types",
        sa.Column("type_name", sa.String(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.PrimaryKeyConstraint("type_name", "worker_id"),
    )
    op.create_table(
        "worker_permitted_users",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "worker_id"),
    )
    job_policy = postgresql.ENUM(
        "PRIVATE",
        "PERMITTED_USERS",
        "PERMITTED_WORKERS",
        "PERMITTED_WORKERS_AND_USERS",
        "ALL",
        name="job_permission_policy",
        create_type=False,
    )
    job_policy.create(op.get_bind(), checkfirst=False)
    op.add_column("jobs", sa.Column("permission_policy", job_policy, nullable=True))
    op.add_column("jobs", sa.Column("user_id", sa.Integer(), nullable=True))

    # A valid hash avoids login errors; its random password is never retained.
    # Only create the inactive account when there are legacy jobs to preserve.
    password_hash = PasswordHash.recommended().hash(secrets.token_urlsafe(32))
    op.execute(
        sa.text("""
        INSERT INTO users (
            username, email, full_name, role, hashed_password, active,
            created_at, updated_at
        )
        SELECT '__legacy_jobs__', 'legacy-jobs@orqbit.invalid',
               'Legacy job owner', 'REGULAR', :password_hash, false,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        WHERE EXISTS (SELECT 1 FROM jobs)
    """).bindparams(password_hash=password_hash)
    )
    op.execute("""
        UPDATE jobs
        SET permission_policy = 'PRIVATE',
            user_id = (SELECT id FROM users WHERE username = '__legacy_jobs__')
    """)
    op.alter_column("jobs", "permission_policy", nullable=False)
    op.alter_column("jobs", "user_id", nullable=False)
    op.create_foreign_key(
        "fk_jobs_user_id_users",
        "jobs",
        "users",
        ["user_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_jobs_user_id_users", "jobs", type_="foreignkey")
    op.drop_column("jobs", "user_id")
    op.drop_column("jobs", "permission_policy")
    op.drop_table("worker_permitted_users")
    op.drop_table("supported_job_types")
    op.drop_table("job_permitted_workers")
    op.drop_table("job_permitted_users")
    op.drop_index(
        "uq_job_attempts_one_running",
        table_name="job_attempts",
        postgresql_where=sa.text("status = 'RUNNING'"),
    )
    op.drop_table("job_attempts")
    op.drop_table("workers")
    op.drop_table("users")
    for name in (
        "job_permission_policy",
        "worker_permission_policy",
        "attemptstatus",
        "userrole",
    ):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=False)
