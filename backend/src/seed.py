"""Populate or clear a development database using the existing application schema."""

import argparse
import os
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from database import SessionLocal
from dto.job import JobCreate
from dto.user import UserRegister
from models import (
    Job,
    JobAttempt,
    PermittedUser,
    PermittedWorker,
    SupportedJobType,
    User,
    Worker,
    WorkerPermittedUser,
)
from models.job import JobStatus
from models.job import PermissionPolicy as JobPolicy
from models.job_attempts import AttemptStatus
from models.user import UserRole
from models.worker import PermissionPolicy as WorkerPolicy
from services.job import get_request_fingerprint
from services.job_execution import get_db_now, retry_available_at, retry_backoff
from services.user_auth import get_password_hash
from services.worker_auth import generate_api_key, hash_api_key


def seed_data(session: Session, password: str) -> dict[str, str]:
    """Add demo records; the caller owns commit/rollback. Return new worker keys."""
    accounts = [
        ("demo_admin", "Demo Administrator", UserRole.ADMIN, True),
        ("demo_alice", "Alice Petrova", UserRole.REGULAR, True),
        ("demo_bob", "Bob Ivanov", UserRole.REGULAR, True),
        ("demo_carol", "Carol Dimitrova", UserRole.REGULAR, True),
        ("demo_inactive", "Inactive Account", UserRole.REGULAR, False),
    ]
    if (
        session.scalar(
            select(User.id)
            .where(User.username.in_([row[0] for row in accounts]))
            .limit(1)
        )
        is not None
    ):
        raise ValueError("Demo users already exist. Use reset to clear and reseed.")

    now = get_db_now(session)
    users = []
    for username, full_name, role, active in accounts:
        payload = UserRegister(
            username=username,
            email=f"{username}@example.com",
            full_name=full_name,
            password=password,
        )
        users.append(
            User(
                **payload.model_dump(exclude={"password"}),
                hashed_password=get_password_hash(password),
                role=role,
                active=active,
                created_at=now - timedelta(days=30),
                updated_at=now - timedelta(days=1),
            )
        )
    session.add_all(users)
    session.flush()
    admin, alice, bob, carol, _ = users

    all_types = [
        "add_numbers",
        "count_primes",
        "delay",
        "delay_with_heartbeat",
        "csv_summary",
    ]
    worker_specs = [
        ("demo_math", alice, all_types[:2], WorkerPolicy.PRIVATE, True),
        ("demo_data", bob, ["csv_summary"], WorkerPolicy.PRIVATE, True),
        ("demo_delay", carol, all_types[2:4], WorkerPolicy.PERMITTED_USERS, True),
        ("demo_multi", admin, all_types, WorkerPolicy.ALL, True),
        ("demo_paused", alice, ["add_numbers"], WorkerPolicy.ALL, False),
        ("demo_spare", bob, ["add_numbers", "delay"], WorkerPolicy.ALL, True),
    ]
    workers = []
    keys = {}
    for name, owner, types, policy, active in worker_specs:
        key = generate_api_key()
        keys[name] = key
        workers.append(
            Worker(
                name=name,
                user=owner,
                active=active,
                secret_api_key_hash=hash_api_key(key),
                permission_policy=policy,
                permitted_users=[alice, bob]
                if policy == WorkerPolicy.PERMITTED_USERS
                else [],
                supported_types=[
                    SupportedJobType(
                        type_name=job_type,
                        created_at=now - timedelta(days=20),
                        updated_at=now - timedelta(days=20),
                    )
                    for job_type in types
                ],
                created_at=now - timedelta(days=20),
                updated_at=now - timedelta(days=1),
            )
        )
    session.add_all(workers)
    session.flush()
    math, data, delay, multi, _, _ = workers

    examples = [
        ("add_numbers", {"numbers": [2, -3, 5.5, 0]}, {"sum": 4.5}, math),
        ("count_primes", {"limit": 100}, {"limit": 100, "count": 25}, math),
        ("delay", {}, {"waited_seconds": 5}, delay),
        ("delay_with_heartbeat", {}, {"waited_seconds": 5}, delay),
        (
            "csv_summary",
            {"csv": "amount\n10\n20\n", "columns": ["amount"]},
            {
                "row_count": 2,
                "columns": {
                    "amount": {
                        "count": 2,
                        "sum": 30.0,
                        "min": 10.0,
                        "max": 20.0,
                        "mean": 15.0,
                    }
                },
            },
            data,
        ),
    ]
    scenarios = {
        "pending": [],
        "running": [AttemptStatus.RUNNING],
        "succeeded": [AttemptStatus.SUCCEEDED],
        "failed": [AttemptStatus.FAILED],
        "retry_pending": [AttemptStatus.LOST],
        "retry_succeeded": [AttemptStatus.LOST, AttemptStatus.SUCCEEDED],
        "exhausted": [AttemptStatus.LOST] * 3,
        "expired": [AttemptStatus.RUNNING],
    }
    policies = list(JobPolicy)
    for type_index, (job_type, params, result, worker) in enumerate(examples):
        for scenario_index, (scenario, statuses) in enumerate(scenarios.items()):
            policy = policies[(type_index + scenario_index) % len(policies)]
            payload = JobCreate(
                job_type=job_type,
                params=params,
                permission_policy=policy,
                permitted_user_ids=[admin.id]
                if policy
                in (
                    JobPolicy.PERMITTED_USERS,
                    JobPolicy.PERMITTED_WORKERS_AND_USERS,
                )
                else [],
                permitted_worker_ids=[multi.id]
                if policy
                in (
                    JobPolicy.PERMITTED_WORKERS,
                    JobPolicy.PERMITTED_WORKERS_AND_USERS,
                )
                else [],
            )
            created = now - timedelta(days=type_index + 1, hours=scenario_index)
            job = Job(
                user=worker.user,
                job_type=job_type,
                params=params,
                permission_policy=policy,
                permitted_users=[admin] if payload.permitted_user_ids else [],
                permitted_workers=[multi] if payload.permitted_worker_ids else [],
                idempotency_key=f"demo:{job_type}:{scenario}",
                request_fingerprint=get_request_fingerprint(payload),
                status=JobStatus.PENDING,
                max_attempts=3 if AttemptStatus.LOST in statuses else 1,
                attempts_count=len(statuses),
                available_at=created,
                created_at=created,
                updated_at=created,
            )
            session.add(job)
            start = created + timedelta(minutes=1)
            for number, status in enumerate(statuses, start=1):
                if status == AttemptStatus.RUNNING:
                    start = now - timedelta(minutes=3 if scenario == "expired" else 1)
                lease = start + timedelta(minutes=2)
                updated = lease if status == AttemptStatus.LOST else start
                if status in (AttemptStatus.SUCCEEDED, AttemptStatus.FAILED):
                    updated = start + timedelta(seconds=30)
                attempt = JobAttempt(
                    job=job,
                    worker=worker,
                    attempt_number=number,
                    status=status,
                    params=params,
                    result=result if status == AttemptStatus.SUCCEEDED else None,
                    error={
                        "code": "execution_failed",
                        "message": "Example worker failure",
                    }
                    if status == AttemptStatus.FAILED
                    else None,
                    lease_expires_at=lease,
                    created_at=start,
                    updated_at=updated,
                )
                session.add(attempt)
                job.updated_at = updated
                start = updated + retry_backoff(number)

            if scenario in ("running", "expired"):
                job.status = JobStatus.RUNNING
            elif scenario in ("succeeded", "retry_succeeded"):
                job.status = JobStatus.SUCCEEDED
                job.result = result
            elif scenario == "failed":
                job.status = JobStatus.FAILED
                job.error = attempt.error
            elif scenario == "exhausted":
                job.status = JobStatus.FAILED
                job.error = {
                    "code": "attempts_exhausted",
                    "message": "Maximum attempts reached after lease expiry",
                }
            elif scenario == "retry_pending":
                # Recovery has just closed this attempt and scheduled a retry.
                attempt.created_at = now - timedelta(minutes=3)
                attempt.lease_expires_at = now - timedelta(minutes=1)
                attempt.updated_at = job.updated_at = now
                job.available_at = retry_available_at(now, 1)

    session.flush()
    return keys


def clear_data(session: Session) -> None:
    """Delete ALL application rows, preserving schema, sequences, and migrations."""
    for model in (
        JobAttempt,
        PermittedUser,
        PermittedWorker,
        WorkerPermittedUser,
        SupportedJobType,
        Job,
        Worker,
        User,
    ):
        session.execute(delete(model))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("seed", "clear", "reset"),
        help="seed demo data, clear ALL application data, or clear and reseed",
    )
    args = parser.parse_args()
    password = os.environ.get("ORQBIT_DEMO_PASSWORD", "")
    if args.action != "clear" and not password:
        parser.error("Set ORQBIT_DEMO_PASSWORD for the demo user accounts.")

    try:
        with SessionLocal.begin() as session:
            if args.action in ("clear", "reset"):
                clear_data(session)
            keys = seed_data(session, password) if args.action != "clear" else {}
    except (ValueError, SQLAlchemyError) as error:
        # SQLAlchemy errors can contain connection details and bound parameters.
        parser.exit(
            1,
            f"Operation rolled back ({type(error).__name__}). "
            "Check configuration, migrations, password rules, and demo name conflicts.\n",
        )

    if keys:
        print("Created 5 users, 6 workers, 40 jobs, and 50 attempts.")
        print("Generated worker API keys (shown only now):")
        for name, key in keys.items():
            print(f"  {name}: {key}")
    else:
        print("All application data cleared; schema and migrations preserved.")


if __name__ == "__main__":
    main()
