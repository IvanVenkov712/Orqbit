from datetime import datetime
from typing import Any

from pydantic import BaseModel, HttpUrl

from dto.jobs import JobStatus

class CreateJobRequest(BaseModel):
    webhook_url: HttpUrl
    type: str
    payload: dict[str, Any]

class CreateJobResponse(BaseModel):
    job_id: int
    status: JobStatus

class JobResponse(BaseModel):
    job_id: int
    status: JobStatus
    result: str | dict[str, Any] | None = None
    created_at: datetime
    finished_at: datetime = None
