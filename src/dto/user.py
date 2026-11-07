from pydantic import BaseModel, ConfigDict

from models.user import UserRole


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    active: bool
    role: UserRole

    model_config = ConfigDict(from_attributes=True)

class UserRegister(BaseModel):
    username: str
    email: str
    full_name: str
    password: str

    model_config = ConfigDict(from_attributes=True)

