from pydantic import PositiveInt, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: PostgresDsn
    lease_seconds: PositiveInt
    protraction_seconds: PositiveInt

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: PostgresDsn) -> PostgresDsn:
        if value.scheme != "postgresql+psycopg":
            raise ValueError(
                "DATABASE_URL must use postgresql+psycopg"
            )

        if not value.path or value.path == "/":
            raise ValueError("DATABASE_URL must include a database name")

        return value

settings = Settings()