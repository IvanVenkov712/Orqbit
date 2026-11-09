from pydantic import BaseModel, ConfigDict, JsonValue


class CompleteJob(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    result: dict[str, JsonValue]


class FailJob(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    error: dict[str, JsonValue]
