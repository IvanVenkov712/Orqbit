import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from .job_attempts import JobAttempt
    from .supported_types import SupportedJobType
    from .user import User
    from .worker_permitted_users import WorkerPermittedUser


class PermissionPolicy(enum.Enum):
    PRIVATE = "PRIVATE"
    PERMITTED_USERS = "PERMITTED_USERS"
    ALL = "ALL"


class Worker(Base, TimestampMixin):

    __tablename__ = "workers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    active: Mapped[bool] = mapped_column(default=True)
    secret_api_key_hash: Mapped[str] = mapped_column(unique=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    
    permission_policy: Mapped[PermissionPolicy] = mapped_column(
        Enum(PermissionPolicy), default=PermissionPolicy.ALL
    )

    user: Mapped["User"] = relationship(
        back_populates="workers"
    )
    
    attempts: Mapped[list["JobAttempt"]] = relationship(
        back_populates="worker",
        passive_deletes="all",
    )
    
    supported_types: Mapped[list["SupportedJobType"]] = relationship(
        back_populates="worker",
        cascade="all, delete-orphan"
    )
    
    permitted_users: Mapped[list["WorkerPermittedUser"]] = relationship(
        back_populates="worker",
        cascade="all, delete-orphan"
    )
    

    