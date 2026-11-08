from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from models.worker import PermissionPolicy


class WorkerBase(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,16}$")
    supported_types: set[str] = Field(min_length=1)
    permission_policy: PermissionPolicy
    permitted_user_ids: list[PositiveInt] = Field(default_factory=list)

class WorkerCreate(WorkerBase):
    pass

class WorkerRead(WorkerBase):
    id: PositiveInt
    active: bool
    user_id: int
    
    model_config = ConfigDict(from_attributes=True)
    
class WorkerCreateResponse(WorkerRead):
    secret_api_key: str

    model_config = ConfigDict(from_attributes=True)
