from typing import Any

from pydantic import AliasChoices, AliasPath, BaseModel, ConfigDict, Field

from models.job_attempts import AttemptStatus


class JobAttemptBase(BaseModel):
    id: int
    job_id: int
    job_type: str
    attempt_number: int
    status: AttemptStatus
    params: dict[str, Any]
    

class JobAttemptRead(JobAttemptBase):
    model_config = ConfigDict(from_attributes=True)

    job_type: str = Field(
        validation_alias=AliasChoices(
            "job_type",
            AliasPath("job", "job_type"),
        )
    )