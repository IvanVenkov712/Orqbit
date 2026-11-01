from enum import Enum

from pydantic import BaseModel


class JobStatus(BaseModel, Enum, str):
    PENDING = "pending" # Waiting for a worker
    CLAIMED = "claimed" # The job was assigned to a worker
    WORKING = "running" # The worker began working on the job
    FINISHED = "finished" # The worker finished working on the job
    FAILED = "failed" # The worker failed finishing the job