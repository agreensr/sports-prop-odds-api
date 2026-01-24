"""
Application configuration.
"""
import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

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

    # Database - load from environment with fallback
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/nba_props")

    # NBA API (nba_api library)
    NBA_API_CACHE_TTL: int = 300  # 5 minutes
    NBA_API_TIMEOUT: int = 30  # 30 seconds

    # The Odds API
    THE_ODDS_API_KEY: str = ""
    ODDS_API_REGIONS: str = "us"  # us, uk, eu, au
    ODDS_API_CACHE_TTL: int = 600  # 10 minutes

    # CORS
    CORS_ORIGINS: list = ["*"]

    # Logging
    LOG_LEVEL: str = "INFO"

    # Legacy/compatibility fields (allow but don't require)
    MODEL_VERSION: str = "1.0.0"
    TRAINING_MIN_GAMES: int = 20


settings = Settings()
