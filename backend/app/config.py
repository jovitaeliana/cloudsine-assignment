from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    virustotal_api_key: str
    gemini_api_key: str
    database_url: str = Field(..., alias="DATABASE_URL")
    environment: str = "development"
    cors_allowed_origins_raw: str = Field(
        "http://localhost:5173", alias="CORS_ALLOWED_ORIGINS"
    )

    max_upload_bytes: int = 32 * 1024 * 1024
    scan_poll_timeout_seconds: int = 180
    vt_base_url: str = "https://www.virustotal.com/api/v3"
    gemini_model: str = "gemini-2.5-flash"

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [s.strip() for s in self.cors_allowed_origins_raw.split(",") if s.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
