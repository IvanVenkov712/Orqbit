from datetime import datetime
from typing import Any

from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field

from models.job_attempts import AttemptStatus


class JobAttemptBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_type: str = Field(
        validation_alias=AliasChoices(
            "job_type",
            AliasPath("job", "job_type"),
        )
    )
    id: int
    job_id: int
    attempt_number: int
    status: AttemptStatus
    params: dict[str, Any]
    lease_expires_at: datetime

class JobAttemptClaim(JobAttemptBase):
   pass

class JobAttemptRead(JobAttemptBase):
    created_at: datetime
    updated_at: datetime
    worker_id: int
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None