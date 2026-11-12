"""Demo data and cleanup against the real migrated PostgreSQL schema."""

import sys

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

import seed
from dto.job import JobCreate
from models import Job, JobAttempt, Producer, User, Worker
from models.base import Base
from models.job import JobStatus
from models.job import PermissionPolicy as JobPolicy
from models.job_attempts import AttemptStatus
from models.user import UserRole
from models.worker import PermissionPolicy as WorkerPolicy
from services.job import get_request_fingerprint, job_accessible_for_worker
from services.user_auth import authenticate_user, verify_password
from services.worker_auth import hash_api_key

PASSWORD = "ExamplePass7$"


def table_counts(session):
    return {
        table.name: session.scalar(select(func.count()).select_from(table))
        for table in Base.metadata.sorted_tables
    }


def test_seed_creates_varied_consistent_data(database, monkeypatch):
    with Session(database) as session, session.begin():
        now = seed.get_db_now(session)
        monkeypatch.setattr(seed, "get_db_now", lambda session: now)
        keys = seed.seed_data(session, PASSWORD)

    with Session(database) as session:
        users = session.scalars(select(User)).all()
        workers = session.scalars(select(Worker)).all()
        producers = session.scalars(select(Producer)).all()
        jobs = session.scalars(select(Job)).all()
        attempts = session.scalars(select(JobAttempt)).all()
        assert (len(users), len(workers), len(jobs), len(attempts)) == (5, 6, 40, 50)
        assert {user.role for user in users} == set(UserRole)
        assert {user.active for user in users} == {True, False}
        assert all(verify_password(PASSWORD, user.hashed_password) for user in users)
        assert authenticate_user(session, "demo_admin", PASSWORD).role == UserRole.ADMIN
        assert authenticate_user(session, "demo_inactive", PASSWORD) is None
        assert {worker.active for worker in workers} == {True, False}
        assert {worker.permission_policy for worker in workers} == {
            WorkerPolicy.PRIVATE,
            WorkerPolicy.PERMITTED_USERS,
            WorkerPolicy.ALL,
        }
        assert all(
            worker.secret_api_key_hash == hash_api_key(keys[worker.name])
            for worker in workers
        )
        assert {
            producer.name: (producer.user.username, producer.active)
            for producer in producers
        } == {
            "demo_reports": ("demo_alice", True),
            "demo_imports": ("demo_bob", True),
            "demo_scheduler": ("demo_carol", True),
            "demo_disabled": ("demo_alice", False),
        }
        assert all(
            producer.secret_api_key_hash == hash_api_key(keys[producer.name])
            and producer.secret_api_key_hash != keys[producer.name]
            for producer in producers
        )
        assert len(keys) == len(set(keys.values())) == len(workers) + len(producers)
        assert any(len(worker.supported_types) > 1 for worker in workers)
        assert any(worker.permitted_users for worker in workers)
        assert {job.status for job in jobs} == set(JobStatus)
        assert {job.permission_policy for job in jobs} == set(JobPolicy)
        assert {attempt.status for attempt in attempts} == set(AttemptStatus)
        assert {job.job_type for job in jobs} == {
            "add_numbers",
            "count_primes",
            "delay",
            "delay_with_heartbeat",
            "csv_summary",
        }
        assert any(
            job.status == JobStatus.PENDING and job.available_at > now for job in jobs
        )
        assert any(
            attempt.status == AttemptStatus.RUNNING and attempt.lease_expires_at < now
            for attempt in attempts
        )
        assert any(
            attempt.status == AttemptStatus.RUNNING and attempt.lease_expires_at > now
            for attempt in attempts
        )
        assert any(
            job.status == JobStatus.SUCCEEDED and len(job.attempts) > 1 for job in jobs
        )

        for job in jobs:
            history = sorted(job.attempts, key=lambda attempt: attempt.attempt_number)
            assert job.attempts_count == len(history) <= job.max_attempts
            assert [attempt.attempt_number for attempt in history] == list(
                range(1, len(history) + 1)
            )
            assert job.created_at <= job.updated_at
            assert job.request_fingerprint == get_request_fingerprint(
                JobCreate(
                    job_type=job.job_type,
                    params=job.params,
                    permission_policy=job.permission_policy,
                    permitted_user_ids=[user.id for user in job.permitted_users],
                    permitted_worker_ids=[
                        worker.id for worker in job.permitted_workers
                    ],
                )
            )
            for attempt in history:
                assert attempt.params == job.params
                assert attempt.created_at <= attempt.updated_at
                assert attempt.created_at < attempt.lease_expires_at
                assert job_accessible_for_worker(job, attempt.worker)
                assert job.job_type in {
                    item.type_name for item in attempt.worker.supported_types
                }
            if job.status == JobStatus.PENDING:
                assert not history or history[-1].status == AttemptStatus.LOST
                assert job.attempts_count < job.max_attempts
                assert job.result is job.error is None
            elif job.status == JobStatus.RUNNING:
                assert history[-1].status == AttemptStatus.RUNNING
                assert (
                    sum(item.status == AttemptStatus.RUNNING for item in history) == 1
                )
                assert job.result is job.error is None
            elif job.status == JobStatus.SUCCEEDED:
                assert history[-1].status == AttemptStatus.SUCCEEDED
                assert job.result == history[-1].result
                assert job.result is not None and job.error is None
            elif history[-1].status == AttemptStatus.FAILED:
                assert job.error == history[-1].error
                assert job.error is not None and job.result is None
            else:
                assert all(item.status == AttemptStatus.LOST for item in history)
                assert job.attempts_count == job.max_attempts
                assert job.error["code"] == "attempts_exhausted"


def test_clear_removes_all_data_but_preserves_schema_and_migrations(database, user):
    with Session(database) as session, session.begin():
        seed.seed_data(session, PASSWORD)

    with Session(database) as session, session.begin():
        revision = session.scalar(text("SELECT version_num FROM alembic_version"))
        seed.clear_data(session)

    with Session(database) as session, session.begin():
        assert all(count == 0 for count in table_counts(session).values())
        assert (
            session.scalar(text("SELECT version_num FROM alembic_version")) == revision
        )
        # Clearing an empty database is safe, and reseeding needs no migrations.
        seed.clear_data(session)
        seed.seed_data(session, PASSWORD)

    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 40


@pytest.fixture
def seed_cli(database, monkeypatch):
    monkeypatch.setattr(seed, "SessionLocal", sessionmaker(bind=database))
    monkeypatch.setenv("ORQBIT_DEMO_PASSWORD", PASSWORD)

    def run(action):
        monkeypatch.setattr(sys, "argv", ["seed.py", action])
        seed.main()

    return run


def test_cli_seed_rejects_duplicates_without_changing_data(seed_cli, database, capsys):
    seed_cli("seed")
    output = capsys.readouterr().out
    assert "40 jobs" in output
    assert "4 producers" in output
    assert "demo_math: oqb_" in output
    assert "demo_reports: oqb_" in output
    assert PASSWORD not in output
    with Session(database) as session:
        before = table_counts(session)
    with pytest.raises(SystemExit) as error:
        seed_cli("seed")
    assert error.value.code == 1
    with Session(database) as session:
        assert table_counts(session) == before


def test_cli_reset_and_clear(seed_cli, database, user, monkeypatch):
    seed_cli("seed")
    seed_cli("reset")
    with Session(database) as session:
        assert session.get(User, user.id) is None
        assert session.scalar(select(func.count()).select_from(Job)) == 40
        assert session.scalar(select(func.count()).select_from(JobAttempt)) == 50
        assert session.scalar(select(func.count()).select_from(Producer)) == 4
    monkeypatch.delenv("ORQBIT_DEMO_PASSWORD")
    seed_cli("clear")
    with Session(database) as session:
        assert all(count == 0 for count in table_counts(session).values())


def test_failed_reset_rolls_back_deletions_and_partial_seed(
    seed_cli,
    database,
    monkeypatch,
    capsys,
):
    seed_cli("seed")
    capsys.readouterr()
    with Session(database) as session:
        before = table_counts(session)
        original_ids = set(session.scalars(select(Job.id)))
        original_keys = set(session.scalars(select(Worker.secret_api_key_hash)))
        original_producer_keys = set(
            session.scalars(select(Producer.secret_api_key_hash))
        )

    real_seed = seed.seed_data

    def fail_after_inserts(session, password):
        real_seed(session, password)
        raise ValueError("Sensitive error details must not be printed")

    monkeypatch.setattr(seed, "seed_data", fail_after_inserts)
    with pytest.raises(SystemExit) as error:
        seed_cli("reset")
    assert error.value.code == 1
    assert "Sensitive error" not in capsys.readouterr().err
    with Session(database) as session:
        assert table_counts(session) == before
        assert set(session.scalars(select(Job.id))) == original_ids
        assert set(session.scalars(select(Worker.secret_api_key_hash))) == original_keys
        assert (
            set(session.scalars(select(Producer.secret_api_key_hash)))
            == original_producer_keys
        )


@pytest.mark.parametrize("password", [None, "invalid"])
def test_seed_requires_valid_password(seed_cli, database, monkeypatch, password):
    if password is None:
        monkeypatch.delenv("ORQBIT_DEMO_PASSWORD")
    else:
        monkeypatch.setenv("ORQBIT_DEMO_PASSWORD", password)
    with pytest.raises(SystemExit):
        seed_cli("seed")
    with Session(database) as session:
        assert all(count == 0 for count in table_counts(session).values())
