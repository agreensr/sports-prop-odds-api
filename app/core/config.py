"""
Application configuration.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field

# Get the project root directory (3 levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    """Application settings."""

    model_config = ConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Allow extra fields from .env
    )

    # Application
    APP_NAME: str = "NBA Player Prop Prediction API"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8001

    # Database - REQUIRED: must be set via environment variable
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://REQUIRED:REQUIRED@REQUIRED:REQUIRED/REQUIRED"
    )

    # NBA API (nba_api library)
    NBA_API_CACHE_TTL: int = 300  # 5 minutes
    NBA_API_TIMEOUT: int = 30  # 30 seconds
    NBA_API_REQUEST_DELAY: float = 0.6  # Delay between requests to respect rate limits
    CURRENT_SEASON: str = "2025-26"  # Current NBA season

    # The Odds API
    THE_ODDS_API_KEY: str = ""
    ODDS_API_REGIONS: str = "us"  # us, uk, eu, au
    ODDS_API_CACHE_TTL: int = 600  # 10 minutes

    # CORS - Comma-separated list of allowed origins
    CORS_ORIGINS: list = Field(
        default_factory=lambda: (
            os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        )
    )

    # Logging
    LOG_LEVEL: str = "INFO"

    # Legacy/compatibility fields (allow but don't require)
    MODEL_VERSION: str = "1.0.0"
    TRAINING_MIN_GAMES: int = 20


settings = Settings()
