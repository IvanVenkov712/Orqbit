from datetime import datetime
from typing import Any

from pydantic import (
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    PositiveInt,
    field_validator,
)

from models.job import JobStatus, PermissionPolicy
from models.job_attempts import JobAttempt


class JobCreate(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    job_type: str = Field(min_length=1, max_length=100, pattern=r"\S")
    params: dict[str, JsonValue]
    permission_policy: PermissionPolicy
    
    permitted_user_ids: list[PositiveInt] = Field(default_factory=list)
    permitted_worker_ids: list[PositiveInt] = Field(default_factory=list)


class JobSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    owner_username: str = Field(validation_alias=AliasPath("user", "username"))
    job_type: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    owner_username: str = Field(validation_alias=AliasPath("user", "username"))
    producer_name: str | None = Field(
        default=None, validation_alias=AliasPath("producer", "name")
    )
    job_type: str
    params: dict[str, Any]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    status: JobStatus
    attempt_ids: list[int] = Field(validation_alias="attempts")
    max_attempts: int
    attempts_count: int
    available_at: datetime
    created_at: datetime
    updated_at: datetime

    @field_validator("attempt_ids", mode="before")
    @classmethod
    def read_attempt_ids(cls, attempts: list[JobAttempt]) -> list[int]:
        return [attempt.id for attempt in attempts]
