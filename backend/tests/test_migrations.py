import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from models.job import Job, JobStatus
from models.job_attempts import AttemptStatus, JobAttempt
from models.user import User


def test_alembic_metadata_registers_producer_in_fresh_process():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from models.base import Base; "
            "assert 'producers' in {table.name for table in Base.metadata.sorted_tables}; "
            "fk = next(iter(Base.metadata.tables['jobs'].c.producer_id.foreign_keys)); "
            "assert fk.column is Base.metadata.tables['producers'].c.id",
        ],
        cwd=Path(__file__).resolve().parents[1] / "src",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


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


def test_lease_upgrade_preserves_terminal_attempts(
    database, alembic_config, user, claim_worker
):
    worker, _ = claim_worker
    old_time = datetime(2020, 1, 1, tzinfo=UTC)
    with Session(database) as session:
        session.add(
            Job(
                job_type="example",
                params={"input": True},
                status=JobStatus.FAILED,
                user_id=user.id,
                idempotency_key="lease-migration",
                request_fingerprint="test-fingerprint",
                attempts=[
                    JobAttempt(
                        worker_id=worker.id,
                        attempt_number=number,
                        status=status,
                        params={"number": number},
                        result={"value": 3}
                        if status == AttemptStatus.SUCCEEDED
                        else None,
                        error={"message": "failed"}
                        if status == AttemptStatus.FAILED
                        else None,
                        created_at=old_time,
                        updated_at=old_time + timedelta(hours=number),
                    )
                    for number, status in enumerate(
                        (
                            AttemptStatus.SUCCEEDED,
                            AttemptStatus.FAILED,
                            AttemptStatus.LOST,
                        ),
                        start=1,
                    )
                ],
            )
        )
        session.commit()

    try:
        command.downgrade(alembic_config, "4610066358ca")
        with database.connect() as connection:
            original = (
                connection.execute(text("SELECT * FROM job_attempts ORDER BY id"))
                .mappings()
                .all()
            )

        command.upgrade(alembic_config, "head")
        with database.connect() as connection:
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("job_attempts")
            }
            assert columns["lease_expires_at"]["nullable"] is False
            assert columns["lease_expires_at"]["type"].timezone is True
            assert columns["lease_expires_at"]["default"] is None
            migrated = (
                connection.execute(text("SELECT * FROM job_attempts ORDER BY id"))
                .mappings()
                .all()
            )
            assert len(migrated) == len(original) == 3
            for before, after in zip(original, migrated, strict=True):
                values = dict(after)
                assert values.pop("lease_expires_at") == before["updated_at"]
                assert values == dict(before)

        command.check(alembic_config)
    finally:
        command.upgrade(alembic_config, "head")


def test_lease_upgrade_rejects_running_attempts_without_partial_changes(
    database, alembic_config, user, claim_worker
):
    worker, _ = claim_worker
    with Session(database) as session:
        session.add(
            Job(
                job_type="example",
                params={},
                status=JobStatus.RUNNING,
                user_id=user.id,
                idempotency_key="running-lease-migration",
                request_fingerprint="test-fingerprint",
                attempts=[JobAttempt(worker_id=worker.id, attempt_number=1, params={})],
            )
        )
        session.commit()

    try:
        command.downgrade(alembic_config, "4610066358ca")
        with database.connect() as connection:
            original = (
                connection.execute(text("SELECT * FROM job_attempts")).mappings().one()
            )

        with pytest.raises(DBAPIError, match="Resolve legacy RUNNING attempts"):
            command.upgrade(alembic_config, "head")

        with database.connect() as connection:
            assert MigrationContext.configure(connection).get_current_revision() == (
                "4610066358ca"
            )
            assert "lease_expires_at" not in {
                column["name"]
                for column in inspect(connection).get_columns("job_attempts")
            }
            assert (
                connection.execute(text("SELECT * FROM job_attempts")).mappings().one()
                == original
            )
            assert connection.scalar(text("SELECT status FROM jobs")) == "RUNNING"
    finally:
        # Resolve the legacy attempt before restoring the schema for fixture cleanup.
        with database.begin() as connection:
            connection.execute(text("UPDATE job_attempts SET status = 'FAILED'"))
            connection.execute(text("UPDATE jobs SET status = 'FAILED'"))
        command.upgrade(alembic_config, "head")


def test_retry_upgrade_backfills_counters_without_changing_jobs_or_attempts(
    database, alembic_config, claim_worker, job_factory, monkeypatch
):
    from config import settings

    worker, _ = claim_worker
    with Session(database) as session:
        jobs = [
            job_factory(),
            job_factory(
                status=JobStatus.SUCCEEDED,
                result={"ok": True},
                attempts_count=1,
                max_attempts=1,
                attempts=[
                    JobAttempt(
                        worker_id=worker.id,
                        attempt_number=1,
                        status=AttemptStatus.SUCCEEDED,
                        params={},
                        result={"ok": True},
                    )
                ],
            ),
            job_factory(
                status=JobStatus.RUNNING,
                attempts_count=3,
                max_attempts=3,
                # Gaps must not cause the next attempt number to be reused.
                attempts=[
                    JobAttempt(
                        worker_id=worker.id,
                        attempt_number=number,
                        status=status,
                        params={"number": number},
                    )
                    for number, status in (
                        (1, AttemptStatus.LOST),
                        (3, AttemptStatus.RUNNING),
                    )
                ],
            ),
        ]
        session.add_all(jobs)
        session.commit()
        expected_counts = {
            jobs[0].id: (0, 1),
            jobs[1].id: (1, 1),
            jobs[2].id: (3, 3),
        }

    monkeypatch.setattr(settings, "max_attempts", 5)
    try:
        command.downgrade(alembic_config, "43dcc043466c")
        with database.connect() as connection:
            inspector = inspect(connection)
            assert {"max_attempts", "attempts_count", "available_at"}.isdisjoint(
                column["name"] for column in inspector.get_columns("jobs")
            )
            assert {
                "ck_jobs_positive_max_attempts",
                "ck_jobs_attempts_count_within_limit",
            }.isdisjoint(
                constraint["name"]
                for constraint in inspector.get_check_constraints("jobs")
            )
            original_jobs = (
                connection.execute(text("SELECT * FROM jobs ORDER BY id"))
                .mappings()
                .all()
            )
            original_attempts = (
                connection.execute(text("SELECT * FROM job_attempts ORDER BY id"))
                .mappings()
                .all()
            )
            before_upgrade = connection.scalar(text("SELECT clock_timestamp()"))

        command.upgrade(alembic_config, "head")
        with database.connect() as connection:
            after_upgrade = connection.scalar(text("SELECT clock_timestamp()"))
            columns = {
                column["name"]: column
                for column in inspect(connection).get_columns("jobs")
            }
            for name in ("max_attempts", "attempts_count", "available_at"):
                assert columns[name]["nullable"] is False
            assert columns["max_attempts"]["default"] is None
            assert columns["attempts_count"]["default"] is None
            assert "clock_timestamp()" in columns["available_at"]["default"]
            assert columns["available_at"]["type"].timezone is True
            migrated_jobs = (
                connection.execute(text("SELECT * FROM jobs ORDER BY id"))
                .mappings()
                .all()
            )
            for before, after in zip(original_jobs, migrated_jobs, strict=True):
                values = dict(after)
                assert (
                    values.pop("attempts_count"),
                    values.pop("max_attempts"),
                ) == expected_counts[before["id"]]
                assert before_upgrade <= values.pop("available_at") <= after_upgrade
                assert values == dict(before)
            assert (
                connection.execute(text("SELECT * FROM job_attempts ORDER BY id"))
                .mappings()
                .all()
                == original_attempts
            )

        # The fixed historical backfill must not change defaults for new jobs.
        with Session(database) as session:
            job = job_factory()
            session.add(job)
            session.commit()
            assert job.max_attempts == 5
            assert job.attempts_count == 0
            assert job.available_at is not None
        command.check(alembic_config)
    finally:
        command.upgrade(alembic_config, "head")


@pytest.mark.parametrize(
    ("column", "value", "constraint"),
    [
        ("max_attempts", 0, "ck_jobs_positive_max_attempts"),
        ("attempts_count", -1, "ck_jobs_attempts_count_within_limit"),
        ("attempts_count", 2, "ck_jobs_attempts_count_within_limit"),
    ],
)
def test_retry_constraints_reject_invalid_counters(
    database, job_factory, column, value, constraint
):
    with Session(database) as session:
        job = job_factory(max_attempts=1)
        session.add(job)
        session.commit()
        job_id = job.id
        with pytest.raises(IntegrityError) as raised:
            setattr(job, column, value)
            session.commit()
        session.rollback()
        assert raised.value.orig.sqlstate == "23514"
        assert raised.value.orig.diag.constraint_name == constraint
        job = session.get(Job, job_id)
        assert job.attempts_count == 0
        assert job.max_attempts == 1
