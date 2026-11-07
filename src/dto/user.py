from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.user import UserRole


class UserBase(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,16}$")
    email: EmailStr
    full_name: str


class UserRead(UserBase):
    id: int
    active: bool
    role: UserRole

    model_config = ConfigDict(from_attributes=True)

class UserRegister(UserBase):
    password: str = Field(pattern=r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$#%])[A-Za-z\d@$#%]{6,20}$")
