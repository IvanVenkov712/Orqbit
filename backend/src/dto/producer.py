from pydantic import BaseModel, ConfigDict, Field, PositiveInt


class ProducerAPIKeyResponse(BaseModel):
    secret_api_key: str


class ProducerBase(BaseModel):
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]{3,16}$")


class ProducerCreate(ProducerBase):
    pass


class ProducerRead(ProducerBase):
    id: PositiveInt
    active: bool
    user_id: int
    owner_username: str

    model_config = ConfigDict(from_attributes=True)


class ProducerCreateResponse(ProducerRead):
    secret_api_key: str
