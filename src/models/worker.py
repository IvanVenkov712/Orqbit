from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job_attempts import JobAttempt
    from .supported_types import SupportedJobType
    from .user import User


class Worker(Base, TimestampMixin):

    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    secret_api_key: Mapped[str] = mapped_column(unique=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    user: Mapped["User"] = relationship(
        back_populates="workers"
    )
    
    attempts: Mapped[list["JobAttempt"]] = relationship(
        back_populates="worker"
    )
    
    supported_types: Mapped[list["SupportedJobType"]] = relationship(
        back_populates="worker",
        cascade="all, delete-orphan"
    )

    