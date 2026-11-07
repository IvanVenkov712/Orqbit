import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job import Job
    from .worker import Worker


class UserRole(enum.Enum):
    ADMIN = "ADMIN"
    REGULAR = "REGULAR"

class User(Base, TimestampMixin):

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str] = mapped_column(unique=True)
    full_name: Mapped[str] = mapped_column()

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.REGULAR
    )

    hashed_password: Mapped[str] = mapped_column()
    active: Mapped[bool] = mapped_column(default=True)

    jobs: Mapped[list["Job"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    workers: Mapped[list["Worker"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
