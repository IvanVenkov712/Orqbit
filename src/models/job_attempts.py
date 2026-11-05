import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
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
    
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    job: Mapped["Job"] = relationship(back_populates="jobs")

    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"))
    worker: Mapped["Worker"] = relationship(back_populates="workers")
    
    __table_args__ = {
        UniqueConstraint("job_id", "attempt_number")
    }
    
    