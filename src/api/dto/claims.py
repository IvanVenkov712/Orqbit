from typing import Any

from pydantic import BaseModel


class ClaimJob(BaseModel):
    supported_types: list[str]

class CompleteJob(BaseModel):
    result: dict[str, Any]

class FailJob(BaseModel):
    error: dict[str, Any]