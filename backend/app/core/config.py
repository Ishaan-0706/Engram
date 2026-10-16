from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    FALKORDB_HOST: str = "localhost"
    FALKORDB_PORT: int = 6379
    REDIS_URL: str = "redis://localhost:6379/0"
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    TURN_TTL_SECONDS: int = 7200
    PROPOSAL_LOCK_TTL_SECONDS: int = 30
    GRAPH_QUERY_TIMEOUT_MS: int = 2500
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o"


settings = Settings()
