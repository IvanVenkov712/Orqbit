from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models import Job, User


class Producer(Base, TimestampMixin):
    __tablename__ = "producers"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user: Mapped["User"] = relationship(back_populates="producers")
    jobs: Mapped[list["Job"]] = relationship(
        back_populates="producer", cascade="all, delete-orphan"
    )
    secret_api_key_hash: Mapped[str] = mapped_column(unique=True)
    active: Mapped[bool] = mapped_column(default=True)

