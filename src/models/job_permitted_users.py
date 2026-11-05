from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class PermittedUser(Base, TimestampMixin):

    __tablename__ = "job_permitted_users"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"), primary_key=True
    )