from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .worker import Worker

class SupportedJobType(Base, TimestampMixin):
    __tablename__ = "supported_job_types"

    type_name: Mapped[str] = mapped_column(primary_key=True)
    worker_id: Mapped[int] = mapped_column(ForeignKey("workers.id"), primary_key=True)
    worker: Mapped[Worker] = relationship(back_populates="supported_types")