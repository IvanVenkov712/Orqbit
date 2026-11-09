import pytest
from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from models.job import Job
from models.user import User


def test_migrated_schema_has_postgresql_types(database, alembic_config):
    with database.connect() as connection:
        revision = MigrationContext.configure(connection).get_current_revision()
        assert (
            revision == ScriptDirectory.from_config(alembic_config).get_current_head()
        )

        inspector = inspect(connection)
        assert set(inspector.get_table_names()) == {
            "alembic_version",
            "jobs",
            "users",
            "workers",
            "job_attempts",
            "job_permitted_users",
            "job_permitted_workers",
            "supported_job_types",
            "worker_permitted_users",
        }
        enums = {enum["name"]: enum["labels"] for enum in inspector.get_enums()}
        assert enums["job_permission_policy"] == [
            "PRIVATE",
            "PERMITTED_USERS",
            "PERMITTED_WORKERS",
            "PERMITTED_WORKERS_AND_USERS",
            "ALL",
        ]
        assert enums["worker_permission_policy"] == [
            "PRIVATE",
            "PERMITTED_USERS",
            "ALL",
        ]
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
        for name in (
            "permission_policy",
            "user_id",
            "idempotency_key",
            "request_fingerprint",
        ):
            assert columns[name]["nullable"] is False
        for name in ("idempotency_key", "request_fingerprint"):
            assert columns[name]["default"] is None

    command.check(alembic_config)


def test_repeated_upgrade_preserves_table_and_job(database, alembic_config):
    with Session(database, expire_on_commit=False) as session:
        owner = User(
            username="migration-test",
            email="migration-test@example.com",
            full_name="Migration test",
            hashed_password="unused",
            active=False,
        )
        job = Job(
            job_type="migration-check",
            params={"preserve": [True, None]},
            user=owner,
            idempotency_key="migration-check",
            request_fingerprint="test-fingerprint",
        )
        session.add(job)
        session.commit()
        job_id = job.id
        original_values = (
            job.params,
            job.status,
            job.created_at,
            job.updated_at,
            job.idempotency_key,
            job.request_fingerprint,
        )

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
            job.idempotency_key,
            job.request_fingerprint,
        ) == original_values


def test_idempotency_constraint_scopes_keys_to_creator(database, user):
    with Session(database) as session:
        other = User(
            username="other-creator",
            email="other-creator@example.com",
            full_name="Other creator",
            hashed_password="unused",
        )
        session.add(other)
        session.flush()
        session.add_all(
            [
                Job(
                    job_type="example",
                    params={},
                    user_id=owner_id,
                    idempotency_key="shared-key",
                    request_fingerprint="test-fingerprint",
                )
                for owner_id in (user.id, other.id)
            ]
        )
        session.commit()

        session.add(
            Job(
                job_type="example",
                params={},
                user_id=user.id,
                idempotency_key="shared-key",
                request_fingerprint="test-fingerprint",
            )
        )
        with pytest.raises(IntegrityError) as raised:
            session.commit()
        session.rollback()
        assert raised.value.orig.sqlstate == "23505"
        assert raised.value.orig.diag.constraint_name == "uq_idempotency_key_user_id"


def test_downgrade_removes_new_types_and_allows_reupgrade(database, alembic_config):
    try:
        command.downgrade(alembic_config, "324192f7fa35")
        with database.connect() as connection:
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) == {"alembic_version", "jobs"}
            assert {enum["name"] for enum in inspector.get_enums()} == {"jobstatus"}
    finally:
        command.upgrade(alembic_config, "head")

    with database.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM users")) == 0
    command.check(alembic_config)


def test_upgrade_preserves_legacy_jobs_with_private_inactive_owner(
    database,
    alembic_config,
):
    original_columns = (
        "id, job_type, params, status, result, error, created_at, updated_at"
    )
    try:
        command.downgrade(alembic_config, "324192f7fa35")
        with database.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO jobs (job_type, params, status, result, error,
                                  created_at, updated_at)
                VALUES ('legacy', '{"preserve": [true, null]}', :status,
                        :result, :error,
                        TIMESTAMPTZ '2020-01-01 00:00:00+00',
                        TIMESTAMPTZ '2020-01-02 00:00:00+00')
            """),
                [
                    {"status": "PENDING", "result": None, "error": None},
                    {"status": "SUCCEEDED", "result": '{"ok": true}', "error": None},
                    {"status": "FAILED", "result": None, "error": '{"failed": true}'},
                ],
            )
            original_jobs = connection.execute(
                text(f"SELECT {original_columns} FROM jobs ORDER BY id")
            ).all()

        command.upgrade(alembic_config, "head")
        with database.connect() as connection:
            assert (
                connection.execute(
                    text(f"SELECT {original_columns} FROM jobs ORDER BY id")
                ).all()
                == original_jobs
            )
            owner = connection.execute(text("SELECT * FROM users")).mappings().one()
            assert owner["username"] == "__legacy_jobs__"
            assert owner["active"] is False
            assert owner["role"] == "REGULAR"
            assert owner["hashed_password"].startswith("$argon2id$")
            assert owner["created_at"] is not None
            assert owner["updated_at"] is not None
            assert connection.execute(
                text("SELECT DISTINCT user_id, permission_policy FROM jobs")
            ).all() == [(owner["id"], "PRIVATE")]
            assert connection.scalar(text("SELECT count(*) FROM job_attempts")) == 0
            assert connection.execute(
                text(
                    "SELECT idempotency_key, request_fingerprint FROM jobs ORDER BY id"
                )
            ).all() == [(f"legacy-job:{job.id}", "legacy") for job in original_jobs]
    finally:
        command.upgrade(alembic_config, "head")


def test_upgrade_rejects_legacy_running_jobs_without_partial_changes(
    database,
    alembic_config,
):
    try:
        command.downgrade(alembic_config, "324192f7fa35")
        with database.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO jobs (job_type, params, status, created_at, updated_at)
                VALUES ('legacy', '{}', 'RUNNING', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """)
            )

        with pytest.raises(DBAPIError, match="Resolve legacy RUNNING jobs"):
            command.upgrade(alembic_config, "head")

        with database.connect() as connection:
            assert "users" not in inspect(connection).get_table_names()
            assert connection.scalar(text("SELECT status FROM jobs")) == "RUNNING"
            assert MigrationContext.configure(connection).get_current_revision() == (
                "324192f7fa35"
            )
    finally:
        with database.begin() as connection:
            connection.execute(text("DELETE FROM jobs WHERE status = 'RUNNING'"))
        command.upgrade(alembic_config, "head")
