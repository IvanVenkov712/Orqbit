from typing import Any

from pydantic import BaseModel


class ClaimJobRequest(BaseModel):
    job_types: list[str]

class ClaimJobResponse(BaseModel):
    claim_id: int
    job_id: str
    job_type: str
    payload: dict[str, Any]
    lease_seconds: int

class HeartbeatRequest(BaseModel):
    extend_seconds: int

class CompleteRequest(BaseModel):
    result: str | dict[str, Any]

class FailRequest(BaseModel):
    error_type: str
    error_message: str
    error_details: dict[str, Any]