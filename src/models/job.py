import enum
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job_attempts import JobAttempt
    from .job_permitted_users import PermittedUser
    from .job_permitted_workers import PermittedWorker
    from .user import User


class JobStatus(enum.Enum):
    PENDING = "PENDING" # Waiting for a worker
    RUNNING = "RUNNING" # The worker began working on the job
    SUCCEEDED = "SUCCEEDED" # The worker finished working on the job
    FAILED = "FAILED" # The worker failed finishing the job

class PermissionPolicy(enum.Enum):
    PRIVATE = "PRIVATE" # Visible only for the same user's workers
    PERMITTED_USERS = "PERMITTED_USERS_ONLY" # Visible only for the workers of the permitted users
    PERMITTED_WORKERS = "PERMITTED_WORKERS_ONLY" # Visible only for the permitted workers
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

    permission_policy: Mapped[PermissionPolicy] = mapped_column(
        Enum(PermissionPolicy),
        default=PermissionPolicy.PRIVATE
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    error: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship(back_populates="jobs")
    
    attempts: Mapped[list["JobAttempt"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    
    permitted_users: Mapped[list["PermittedUser"]] = relationship(
        cascade="all, delete-orphan"
    )
    
    permitted_workers: Mapped[list["PermittedWorker"]] = relationship(
        cascade="all, delete-orphan"
    )
