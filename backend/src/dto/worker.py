from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PositiveInt

from models.worker import PermissionPolicy


class WorkerUpdate(BaseModel):
    supported_types: set[
        Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
    ] = Field(min_length=1)
    permission_policy: PermissionPolicy | None = None
    permitted_user_ids: list[PositiveInt] | None = None


class WorkerAPIKeyResponse(BaseModel):
    secret_api_key: str


class WorkerBase(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,16}$")
    supported_types: set[
        Annotated[str, Field(min_length=1, max_length=100, pattern=r"\S")]
    ] = Field(min_length=1)
    permission_policy: PermissionPolicy
    permitted_user_ids: list[PositiveInt] = Field(default_factory=list)

class WorkerCreate(WorkerBase):
    pass

class WorkerRead(WorkerBase):
    id: PositiveInt
    active: bool
    user_id: int
    owner_username: str
    
    model_config = ConfigDict(from_attributes=True)
    
class WorkerCreateResponse(WorkerRead):
    secret_api_key: str

    model_config = ConfigDict(from_attributes=True)
