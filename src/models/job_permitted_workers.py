from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class PermittedWorker(Base, TimestampMixin):
    
    __tablename__ = "job_permitted_workers"
    
    worker_id: Mapped[int] = mapped_column(
        ForeignKey("workers.id"), primary_key=True
    )
    
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"), primary_key=True
    )