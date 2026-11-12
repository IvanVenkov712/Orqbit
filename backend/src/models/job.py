import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from config import settings

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job_attempts import JobAttempt
    from .producers import Producer
    from .user import User
    from .worker import Worker


class JobStatus(enum.Enum):
    PENDING = "PENDING" # Waiting for a worker
    RUNNING = "RUNNING" # The worker began working on the job
    SUCCEEDED = "SUCCEEDED" # The worker finished working on the job
    FAILED = "FAILED" # The worker failed finishing the job

class PermissionPolicy(enum.Enum):
    PRIVATE = "PRIVATE" # Visible only for the same user's workers
    PERMITTED_USERS = "PERMITTED_USERS" # Visible only for the workers of the permitted users
    PERMITTED_WORKERS = "PERMITTED_WORKERS" # Visible only for the permitted workers
    PERMITTED_WORKERS_AND_USERS = "PERMITTED_WORKERS_AND_USERS" # Visible only for the permitted workers
                                                                # and the workers of the permitted users
    ALL = "ALL" # Visible for all workers (dangerous)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus),
        default=JobStatus.PENDING,
    )

    max_attempts: Mapped[int] = mapped_column(default=lambda: settings.max_attempts)
    attempts_count: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
    )

    permission_policy: Mapped[PermissionPolicy] = mapped_column(
        Enum(PermissionPolicy, name="job_permission_policy"),
        default=PermissionPolicy.PRIVATE
    )

    idempotency_key: Mapped[str] = mapped_column(String(100))

    request_fingerprint: Mapped[str] = mapped_column(String(100))

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    error: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship(back_populates="jobs")

    producer_id: Mapped[int | None] = mapped_column(
        ForeignKey("producers.id"), nullable=True, default=None,
    )

    producer: Mapped["Producer | None"] = relationship(back_populates="jobs")

    attempts: Mapped[list["JobAttempt"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    permitted_users: Mapped[list["User"]] = relationship(
        secondary="job_permitted_users"
    )

    permitted_workers: Mapped[list["Worker"]] = relationship(
        secondary="job_permitted_workers"
    )
    
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key"),
        CheckConstraint("max_attempts > 0", name="ck_jobs_positive_max_attempts"),
        CheckConstraint(
            "attempts_count >= 0 AND attempts_count <= max_attempts",
            name="ck_jobs_attempts_count_within_limit",
        ),
        
    )
