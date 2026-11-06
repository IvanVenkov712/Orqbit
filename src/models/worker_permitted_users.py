from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base, TimestampMixin


class WorkerPermittedUser(Base, TimestampMixin):
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )

    worker_id: Mapped[int] = mapped_column(
        ForeignKey("workers.id"), primary_key=True
    )
    