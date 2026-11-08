from typing import Any

from pydantic import BaseModel

from models.job_attempts import AttemptStatus


class JobAttemptBase(BaseModel):
    id: int
    attempt_number: int
    status: AttemptStatus
    params: dict[str, Any]

class JobAttemptRead(JobAttemptBase):
    pass