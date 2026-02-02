"""
Application configuration with environment-specific secrets management.

Supported environment files (loaded in order of precedence):
1. .env.{ENVIRONMENT} (e.g., .env.production, .env.development)
2. .env (fallback)

Required secrets for production:
- DATABASE_URL
- GITHUB_WEBHOOK_SECRET (for webhook security)
"""
import os
import logging
from pathlib import Path
from typing import Optional, Literal
from pydantic_settings import BaseSettings
from pydantic import ConfigDict, Field

# Get the project root directory (3 levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.parent

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings with environment-specific configuration."""

    # Environment
    ENVIRONMENT: Literal["development", "production", "test"] = "development"

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

    # Database - load from environment with secure fallback for development
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5433/sports_bet_ai")

    # Security secrets
    GITHUB_WEBHOOK_SECRET: str = ""
    ADMIN_TOKEN: str = ""

    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_STORAGE: str = "memory"  # "memory" or "redis"
    REDIS_URL: Optional[str] = None  # Required if using Redis storage

    # NBA API (nba_api library)
    NBA_API_CACHE_TTL: int = 300  # 5 minutes
    NBA_API_TIMEOUT: int = 30  # 30 seconds
    NBA_API_REQUEST_DELAY: float = 0.6  # Delay between requests to respect rate limits
    CURRENT_SEASON: str = "2025-26"  # Current NBA season

    # The Odds API
    THE_ODDS_API_KEY: str = ""
    ODDS_API_REGIONS: str = "us"  # us, uk, eu, au
    ODDS_API_CACHE_TTL: int = 600  # 10 minutes

    # CORS - comma-separated string for env var parsing
    CORS_ORIGINS_STR: str = ""  # Environment variable: comma-separated origins

    # Logging
    LOG_LEVEL: str = "INFO"

    # Legacy/compatibility fields (allow but don't require)
    MODEL_VERSION: str = "1.0.0"
    TRAINING_MIN_GAMES: int = 20

    @property
    def CORS_ORIGINS(self) -> list[str]:
        """Get CORS origins with environment-aware defaults."""
        # If env var is set, parse it
        if self.CORS_ORIGINS_STR:
            origins = [o.strip() for o in self.CORS_ORIGINS_STR.split(",") if o.strip()]
            if origins:
                # Reject wildcard in production
                if self.is_production() and "*" in origins:
                    logger.warning(
                        "Wildcard CORS origins (*) are not allowed in production. "
                        "Please set explicit origins in CORS_ORIGINS_STR environment variable."
                    )
                    return []
                return origins

        # Environment-specific defaults
        if self.is_production():
            # Production requires explicit origins
            logger.warning(
                "CORS_ORIGINS_STR not set in production. "
                "Please set CORS_ORIGINS_STR environment variable with explicit origins."
            )
            return []
        else:
            # Development defaults to localhost
            return [
                "http://localhost:3000",
                "http://localhost:8000",
                "http://localhost:8001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
                "http://127.0.0.1:8001",
            ]

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.ENVIRONMENT == "production"

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.ENVIRONMENT == "development"

    def validate_required_secrets(self) -> list[str]:
        """
        Validate that required secrets are set for the current environment.

        Returns:
            List of missing secret names (empty if all present)
        """
        missing = []

        # Database URL is always required
        if not self.DATABASE_URL or self.DATABASE_URL == "postgresql://postgres:postgres@localhost:5433/nba_props":
            if self.is_production():
                missing.append("DATABASE_URL")

        # Webhook secret is required in production
        if self.is_production() and not self.GITHUB_WEBHOOK_SECRET:
            missing.append("GITHUB_WEBHOOK_SECRET")

        # Redis URL is required if using Redis rate limiting
        if self.RATE_LIMIT_ENABLED and self.RATE_LIMIT_STORAGE == "redis" and not self.REDIS_URL:
            missing.append("REDIS_URL")

        return missing

    def get_nba_cache_ttl(self) -> int:
        """
        Get dynamic cache TTL for NBA API based on season status.

        Returns shorter TTL (5 min) during active NBA season (Oct-Jun),
        longer TTL (24 hours) during offseason for better performance.

        Returns:
            Cache TTL in seconds
        """
        from app.utils.timezone import is_in_season

        if is_in_season("nba"):
            return self.NBA_API_CACHE_TTL  # 5 minutes during season
        else:
            return 86400  # 24 hours during offseason

    def get_odds_cache_ttl(self, sport_id: str = "nba") -> int:
        """
        Get dynamic cache TTL for Odds API based on season status.

        Returns shorter TTL during active season, longer TTL during offseason.

        Args:
            sport_id: Sport identifier for season check

        Returns:
            Cache TTL in seconds
        """
        from app.utils.timezone import is_in_season

        if is_in_season(sport_id):
            return self.ODDS_API_CACHE_TTL  # 10 minutes during season
        else:
            return 86400  # 24 hours during offseason


def _load_env_file() -> Path:
    """
    Load the appropriate environment file based on ENVIRONMENT variable.

    Loads in order of precedence:
    1. .env.{ENVIRONMENT} (e.g., .env.production, .env.development)
    2. .env (fallback)
    """
    environment = os.getenv("ENVIRONMENT", "development")

    # Try environment-specific file first
    env_file = PROJECT_ROOT / f".env.{environment}"
    if env_file.exists():
        logger.info(f"Loading environment from {env_file.name}")
        return env_file

    # Fall back to default .env
    default_env = PROJECT_ROOT / ".env"
    if default_env.exists():
        logger.info(f"Loading environment from .env (environment: {environment})")
        return default_env

    logger.warning(f"No environment file found for '{environment}' (checked .env.{environment}, .env)")
    return default_env


# Auto-detect and load environment file
_env_file = _load_env_file()


# Create settings instance with auto-detected env file
class _SettingsWithEnvFile(Settings):
    model_config = ConfigDict(
        env_file=str(_env_file),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = _SettingsWithEnvFile()


# =============================================================================
# DYNAMIC CACHE TTL HELPERS
# =============================================================================

def get_dynamic_cache_ttl(sport_id: str = "nba", default_ttl: int = 300) -> int:
    """
    Get dynamic cache TTL based on whether the sport is in active season.

    During active season: Uses configured TTL for fresh data
    During offseason: Uses longer TTL (24 hours) since data changes less frequently

    Args:
        sport_id: Sport identifier ('nba', 'nfl', 'mlb', 'nhl')
        default_ttl: Fallback TTL if sport not recognized

    Returns:
        Cache TTL in seconds

    Examples:
        >>> # During NBA season (January)
        >>> get_dynamic_cache_ttl('nba')
        300

        >>> # During NBA offseason (August)
        >>> get_dynamic_cache_ttl('nba')
        86400
    """
    from app.utils.timezone import is_in_season

    # Use longer TTL during offseason (24 hours = 86400 seconds)
    OFFSEASON_TTL = 86400

    if not is_in_season(sport_id):
        return OFFSEASON_TTL

    # During season, return sport-specific TTL
    season_ttl = {
        "nba": settings.NBA_API_CACHE_TTL,      # 300 seconds (5 min)
        "nfl": settings.NBA_API_CACHE_TTL * 2,  # 600 seconds (10 min)
        "mlb": settings.NBA_API_CACHE_TTL,      # 300 seconds (5 min)
        "nhl": settings.NBA_API_CACHE_TTL,      # 300 seconds (5 min)
    }

    return season_ttl.get(sport_id, default_ttl)

# Validate secrets on startup
missing_secrets = settings.validate_required_secrets()
if missing_secrets:
    logger.warning(f"Missing required secrets for {settings.ENVIRONMENT}: {', '.join(missing_secrets)}")
    if settings.is_production():
        raise ValueError(
            f"Cannot start in production with missing secrets: {', '.join(missing_secrets)}. "
            f"Please set these environment variables in .env.production"
        )
