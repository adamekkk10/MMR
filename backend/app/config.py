from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RMM_", env_file=".env", extra="ignore")

    # Database (read these from non-prefixed env vars set by docker-compose)
    postgres_user: str = Field(default="rmm", alias="POSTGRES_USER")
    postgres_password: str = Field(default="rmm", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="rmm", alias="POSTGRES_DB")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")

    # Auth / crypto
    secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60

    # Public config
    public_url: str = "http://localhost:8000"
    offline_threshold_seconds: int = 90

    # Bootstrap
    bootstrap_admin_username: str | None = "admin"
    bootstrap_admin_password: str | None = "admin"

    # CORS
    cors_origins: List[str] = ["http://localhost:5173", "http://localhost:8080"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
