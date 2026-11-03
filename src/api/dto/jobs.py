from typing import Any

from pydantic import BaseModel

from models import JobStatus


class JobCreate(BaseModel):
    job_type: str
    params: dict[str, Any]

class JobRead(BaseModel):
    id: int
    job_type: str
    params: dict[str, Any]
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    status: JobStatus
