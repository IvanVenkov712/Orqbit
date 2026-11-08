from typing import Any

from pydantic import BaseModel

from models.job_attempts import AttemptStatus


class JobAttemptBase(BaseModel):
    id: int
    job_id: int
    job_type: str
    attempt_number: int
    status: AttemptStatus
    params: dict[str, Any]

class JobAttemptRead(JobAttemptBase):
    pass
