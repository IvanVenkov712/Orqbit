from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from models import Job


def test_migrated_schema_has_postgresql_types(database, alembic_config):
    with database.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
        assert (
            revision == ScriptDirectory.from_config(alembic_config).get_current_head()
        )

        inspector = inspect(connection)
        columns = {column["name"]: column for column in inspector.get_columns("jobs")}
        for name in ("params", "result", "error"):
            assert isinstance(columns[name]["type"], JSONB)
        assert columns["status"]["type"].enums == [
            "PENDING",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
        ]
        for name in ("created_at", "updated_at"):
            assert columns[name]["type"].timezone is True
            assert columns[name]["nullable"] is False


def test_repeated_upgrade_preserves_table_and_job(database, alembic_config):
    with Session(database, expire_on_commit=False) as session:
        job = Job(job_type="migration-check", params={"preserve": [True, None]})
        session.add(job)
        session.commit()
        job_id = job.id
        original_values = (job.params, job.status, job.created_at, job.updated_at)

    with database.connect() as connection:
        table_oid = connection.scalar(text("SELECT 'jobs'::regclass::oid"))

    command.upgrade(alembic_config, "head")

    with database.connect() as connection:
        assert connection.scalar(text("SELECT 'jobs'::regclass::oid")) == table_oid
    with Session(database) as session:
        job = session.get(Job, job_id)
        assert (
            job.params,
            job.status,
            job.created_at,
            job.updated_at,
        ) == original_values
