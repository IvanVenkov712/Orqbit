import enum
from datetime import datetime, UTC
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

if TYPE_CHECKING:
    from .job import Job
    from .worker import Worker

class AttemptStatus(enum.Enum):
    RUNNING = "RUNNING" # The worker began working on the job
    SUCCEEDED = "SUCCEEDED" # The worker finished working on the job
    FAILED = "FAILED" # The worker failed finishing the job

class JobAttempt(Base):
    
    __tablename__ = "job_attempts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_number: Mapped[int] = mapped_column()
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus), default=AttemptStatus.RUNNING
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

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
    
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    job: Mapped["Job"] = relationship(back_populates="jobs")

    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"))
    worker: Mapped["Worker"] = relationship(back_populates="workers")
    
    __table_args__ = {
        UniqueConstraint("job_id", "attempt_number")
    }
    
    