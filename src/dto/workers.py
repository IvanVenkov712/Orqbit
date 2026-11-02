from typing import Any

from pydantic import BaseModel


class ClaimJobRequest(BaseModel):
    job_types: list[str]

class ClaimJobResponse(BaseModel):
    job_id: str
    job_type: str
    payload: dict[str, Any]
    lease_seconds: int

class HeartbeatRequest(BaseModel):
    extend_seconds: int

class CompleteRequest(BaseModel):
    job_id: int
    result: str | dict[str, Any]

class FailRequest(BaseModel):
    job_id: str
    error_type: str
    error_message: str
    error_details: dict[str, Any]