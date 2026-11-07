from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.user import UserRole


class UserRead(BaseModel):
    id: int
    username: str
    full_name: str
    active: bool
    role: UserRole

    model_config = ConfigDict(from_attributes=True)

class UserRegister(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,16}$")
    email: EmailStr
    password: str = Field(pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$#%])[A-Za-z\d@$#%]{6,20}$")
    full_name: str

    model_config = ConfigDict(from_attributes=True)

