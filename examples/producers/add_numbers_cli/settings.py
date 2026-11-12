"""Producer configuration read from the adjacent .env file."""

from pathlib import Path

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().with_name(".env"),
        extra="ignore",
        hide_input_in_errors=True,
    )

    api_key: SecretStr = Field(min_length=1)
    api_url: AnyHttpUrl
    poll_interval: float = Field(default=2, gt=0, allow_inf_nan=False)
    request_timeout: float = Field(default=10, gt=0, allow_inf_nan=False)
