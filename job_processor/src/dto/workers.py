from pydantic import BaseModel


class ClaimJobRequest(BaseModel):
    job_type: str

class ClaimJobResponse(BaseModel):
    claim_id: int
    job_id: str