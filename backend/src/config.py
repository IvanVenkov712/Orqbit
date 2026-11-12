from pydantic import Field, PositiveInt, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    database_url: PostgresDsn
    lease_seconds: PositiveInt
    lease_extension_seconds: PositiveInt
    max_attempts: PositiveInt = Field(default=1, le=5)
    secret_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    algorithm: str
    access_token_expire_minutes: PositiveInt
    recovery_interval_seconds: PositiveInt
    # Reserve parameters for the fixed predicates and values in recovery UPDATEs.
    recovery_batch_size: PositiveInt = Field(default=1000, le=65530)
    max_unknown_database_errors: PositiveInt = 3

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
