from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PermittedUser(Base):

    __tablename__ = "job_permitted_users"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"), primary_key=True
    )