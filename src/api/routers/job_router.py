import hashlib
import json
from typing import Annotated

import fastapi
from fastapi import Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from database import SessionDep
from dto.job import JobCreate, JobRead
from models.job import Job, JobStatus
from models.user import User
from models.worker import Worker
from services.job import accessible_user_jobs_query, job_accessible_for_user
from services.user_auth import CurrentUser

job_router = fastapi.APIRouter()

def get_permitted_users(
    payload: JobCreate,
    session: SessionDep,
):
    users = session.scalars(
        select(User).where(User.id.in_(payload.permitted_user_ids))
    ).all()
    if len(users) != len(set(payload.permitted_user_ids)):
        raise HTTPException(422, "Some permitted users do not exist")
    
    return list(users)


def get_permitted_workers(
    payload: JobCreate,
    session: SessionDep,
):
    workers = session.scalars(
        select(Worker).where(Worker.id.in_(payload.permitted_worker_ids))
    ).all()

    if len(workers) != len(set(payload.permitted_worker_ids)):
        raise HTTPException(422, "Some permitted workers do not exist")

    return workers

def get_request_fingerprint(payload: JobCreate) -> str:
    request = payload.model_dump(mode="json")
    request["permitted_user_ids"] = sorted(set(payload.permitted_user_ids))
    request["permitted_worker_ids"] = sorted(set(payload.permitted_worker_ids))
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()

@job_router.post(path="/jobs/", response_model=JobRead)
def create_job(
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=100, pattern=r"\S"),
    ],
    payload: JobCreate,
    session: SessionDep,
    user: CurrentUser,
):
    fingerprint = get_request_fingerprint(payload)

    stmt = select(Job).where(
        Job.idempotency_key == idempotency_key,
        Job.user_id == user.id,
    )
    saved = session.scalar(stmt)

    if saved is None:
        job = Job(
            user=user,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            job_type=payload.job_type,
            params=payload.params,
            permission_policy=payload.permission_policy,
            permitted_users=get_permitted_users(payload, session),
            permitted_workers=get_permitted_workers(payload, session),
        )
        session.add(job)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            # A competing submission may have committed the same creator/key.
            saved = session.scalar(stmt)
            if saved is None:
                raise
        else:
            session.refresh(job)
            return job

    if saved.request_fingerprint != fingerprint:
        raise HTTPException(409, "Conflicting create requests")
    return saved

@job_router.get("/jobs", response_model=list[JobRead])
def list_jobs(
    session: SessionDep,
    user: CurrentUser,
    owner_id: int | None = None,
    status: JobStatus | None = None,
    job_type: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    stmt = accessible_user_jobs_query(user).options(selectinload(Job.attempts))

    if owner_id is not None:
        stmt = stmt.where(Job.user_id == owner_id)

    if status is not None:
        stmt = stmt.where(Job.status == status)

    if job_type is not None:
        stmt = stmt.where(Job.job_type == job_type)

    stmt = (
        stmt
        .order_by(Job.id.desc())
        .offset(offset)
        .limit(limit)
    )

    return session.scalars(stmt).all()


@job_router.get(path="/jobs/{job_id}", response_model=JobRead)
def get_job(job_id: int, session: SessionDep, user: CurrentUser):
    job = session.get(Job, job_id)

    if job is None or not job_accessible_for_user(job, user):
        raise HTTPException(404, "Job not found")

    return job



