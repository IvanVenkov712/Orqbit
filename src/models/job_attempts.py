import enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job import Job
    from .worker import Worker

class AttemptStatus(enum.Enum):
    RUNNING = "RUNNING" # The worker began working on the job
    SUCCEEDED = "SUCCEEDED" # The worker finished working on the job
    FAILED = "FAILED" # The worker failed finishing the job
    LOST = "LOST" # The worker stopped responding

class JobAttempt(Base, TimestampMixin):
    
    __tablename__ = "job_attempts"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_number: Mapped[int] = mapped_column()
    status: Mapped[AttemptStatus] = mapped_column(
        Enum(AttemptStatus), default=AttemptStatus.RUNNING
    )

    params: Mapped[dict[str, Any]] = mapped_column(JSONB)

    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    job: Mapped["Job"] = relationship(back_populates="attempts")

    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"))
    worker: Mapped["Worker"] = relationship(back_populates="attempts")

    __table_args__ = (
        UniqueConstraint("job_id", "attempt_number"),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_job_attempts_positive_number",
        ),
        Index(
            "uq_job_attempts_one_running",
            "job_id",
            unique=True,
            postgresql_where=text("status = 'RUNNING'"),
        ),
    )
    
