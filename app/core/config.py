"""Application configuration and environment settings."""
from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings schema."""
    PROJECT_NAME: str = "API Sentinel"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Automated REST API Testing, Regression Detection & AI Diagnostic Platform"
    API_V1_PREFIX: str = "/api/v1"
    
    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Persistence
    DATABASE_URL: str = "sqlite:///./api_sentinel.db"
    
    # Execution Defaults
    DEFAULT_TIMEOUT_SECONDS: float = 10.0
    MAX_CONCURRENCY: int = 10
    
    # AI Engine (Optional - system falls back to heuristics if omitted)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
