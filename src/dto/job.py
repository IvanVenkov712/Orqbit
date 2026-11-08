from typing import Any

from pydantic import BaseModel, Field, PositiveInt

from models.job import JobStatus, PermissionPolicy
from models.job_attempts import JobAttempt


class JobCreate(BaseModel):
    job_type: str
    params: dict[str, Any]
    permission_policy: PermissionPolicy
    
    permitted_user_ids: list[int] = Field(default_factory=list)
    permitted_worker_ids: list[int] = Field(default_factory=list)

class JobRead(BaseModel):
    id: int
    user_id: int
    job_type: str
    params: dict[str, Any]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    status: JobStatus
    attempts: list[JobAttempt]
