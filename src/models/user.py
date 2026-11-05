import enum
from datetime import datetime, UTC
from typing import TYPE_CHECKING

from sqlalchemy import Enum, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .job import Job
    from .worker import Worker


class UserRole(enum.Enum):
    ADMIN = "ADMIN"
    REGULAR = "REGULAR"

class User(Base):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(unique=True)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.REGULAR
    )

    password_hash: Mapped[str] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)

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

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    workers: Mapped[list["Worker"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
