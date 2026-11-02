from datetime import datetime

from sqlmodel import SQLModel, Field

from dto.jobs import JobStatus


class JobBase(SQLModel):
    job_type: str = Field(index=True)
    params: str = Field(index=True)

class Job(JobBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    result: str | None = Field(index=True, default=None)
    created_at: datetime = Field(index=True)
    completed_at: datetime = Field(index=True)
    status: JobStatus = Field(index=True)

class CreateJob(JobBase):
    pass

class CompleteJob(JobBase):
    id: int
    result: str
    status: JobStatus = Field(default=JobStatus.COMPLETED)

class FailJob(JobBase):
    id: int
    status: JobStatus = Field(default=JobStatus.FAILED)