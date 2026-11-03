import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DATE, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class JobStatus(enum.Enum):
    PENDING = "PENDING" # Waiting for a worker
    RUNNING = "RUNNING" # The worker began working on the job
    SUCCEEDED = "SUCCEEDED" # The worker finished working on the job
    FAILED = "FAILED" # The worker failed finishing the job

class Base(DeclarativeBase):
    pass

class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_type: Mapped[str] = mapped_column(String(100))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus),
        default=JobStatus.PENDING,
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    error: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )