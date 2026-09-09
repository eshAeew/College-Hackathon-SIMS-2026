"""Application configuration and environment settings management using Pydantic Settings."""
from functools import lru_cache
from typing import List, Literal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings and runtime environment parameters."""
    
    # Project Identity
    PROJECT_NAME: str = "API Sentinel"
    VERSION: str = "0.1.0"
    DESCRIPTION: str = "Automated REST API Testing, Regression Detection & AI Diagnostic Platform"
    API_V1_PREFIX: str = "/api/v1"
    
    # Environment & Server
    ENVIRONMENT: Literal["development", "testing", "staging", "production"] = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = True
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    
    # CORS Configuration
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]
    
    # Database Persistence
    DATABASE_URL: str = "sqlite:///./api_sentinel.db"
    
    # HTTP Execution Engine Defaults
    DEFAULT_TIMEOUT_SECONDS: float = 10.0
    MAX_CONCURRENCY: int = 10
    MAX_REDIRECTS: int = 5
    
    # Safety & Security Controls
    ALLOW_DESTRUCTIVE_OPERATIONS: bool = False
    ALLOWED_TARGET_HOSTS: List[str] = ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]
    ENFORCE_TARGET_SAFETY: bool = True
    STRICT_TARGET_ALLOWLIST: bool = False
    ALLOW_LOCALHOST_TARGETS: bool = True
    ALLOW_PRIVATE_NETWORK_TARGETS: bool = True
    BLOCK_CLOUD_METADATA: bool = True
    
    # AI Diagnostic Engine (Optional - system falls back to heuristics if omitted)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-flash-latest"
    
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure DATABASE_URL starts with a supported scheme."""
        allowed_prefixes = ("sqlite://", "sqlite+aiosqlite://", "postgresql://", "postgresql+asyncpg://")
        if not any(v.startswith(prefix) for prefix in allowed_prefixes):
            raise ValueError(f"DATABASE_URL must start with one of: {allowed_prefixes}")
        return v

    @field_validator("DEFAULT_TIMEOUT_SECONDS")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Ensure execution timeout is positive."""
        if v <= 0:
            raise ValueError("DEFAULT_TIMEOUT_SECONDS must be greater than 0")
        return v

    @property
    def is_ai_enabled(self) -> bool:
        """Return True if an external Gemini API key is configured."""
        return bool(self.GEMINI_API_KEY and self.GEMINI_API_KEY.strip())

    @property
    def is_production(self) -> bool:
        """Return True if running in production mode."""
        return self.ENVIRONMENT == "production"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear settings cache to reload environment values (useful for tests)."""
    get_settings.cache_clear()
