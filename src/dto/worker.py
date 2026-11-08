from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from models.worker import PermissionPolicy


class WorkerBase(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,16}$")
    supported_types: list[str]
    permission_policy: PermissionPolicy
    permitted_user_ids: list[PositiveInt]

class WorkerCreate(WorkerBase):
    pass

class WorkerRead(BaseModel):
    id: PositiveInt
    active: bool
    user_id: str
    
    model_config = ConfigDict(from_attributes=True)
    
class WorkerCreateResponse(WorkerRead):
    secret_api_key: str

    model_config = ConfigDict(from_attributes=True)
