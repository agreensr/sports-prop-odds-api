"""
Main FastAPI application for NBA Player Prop Prediction API.
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
# Sport-specific routes
from app.api.routes.nba import predictions as nba_predictions, players as nba_players, data as nba_data, odds as nba_odds, injuries as nba_injuries, lineups as nba_lineups, parlays as nba_parlays, historical_odds as nba_historical_odds, opening_odds as nba_opening_odds, minutes_projection as nba_minutes_projection
from app.api.routes.nfl import predictions as nfl_predictions
# Shared routes
from app.api.routes.shared import accuracy, bets
from app.api.routes import sync
from app.api.routes.parlays import router as parlays_router
# Admin routes
from app.api.routes.admin import deploy as admin_deploy

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Start the automation scheduler
    from app.core.scheduler import start_scheduler
    await start_scheduler()
    logger.info("✅ Automation scheduler started")

    # Skip init_db() for existing databases - tables already exist
    # init_db()
    logger.info("Application started")

    yield

    # Shutdown
    from app.core.scheduler import stop_scheduler
    await stop_scheduler()
    logger.info("✅ Automation scheduler stopped")
    logger.info("Shutting down application")


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered player prop predictions for NBA, NFL, and more with official league API integration",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# ROUTE REGISTRATION - SPORT-SPECIFIC ARCHITECTURE
# ============================================================================
#
# IMPORTANT: This codebase uses a sport-specific directory structure.
# When adding new routes, ALWAYS follow this pattern:
#
# 1. Sport-specific routes (NBA, NFL, MLB, etc.):
#    - File: app/api/routes/{sport}/{feature}.py
#    - Router: APIRouter(prefix="/{feature}", tags=["{sport}-{feature}"])
#    - Mount: app.include_router(router, prefix="/api/{sport}")
#    - Result: /api/{sport}/{feature}/...
#
# 2. Shared routes (work for all sports):
#    - File: app/api/routes/shared/{feature}.py
#    - Router: APIRouter(prefix="/api/{feature}", tags=["{feature}"])
#    - Mount: app.include_router(router)  # No prefix added
#    - Result: /api/{feature}/...
#
# Example: Adding NBA feature "player-props"
#   - Create: app/api/routes/nba/player_props.py
#   - Define: router = APIRouter(prefix="/player-props")
#   - Mount: app.include_router(router, prefix="/api/nba")
#   - URL: /api/nba/player-props/...
#
# ⚠️  NEVER add sport-specific features to shared routes!
# ⚠️  ALWAYS use fully-qualified imports: from app.api.routes.nba import ...
#
# ============================================================================

# Include routers with sport-specific prefixes
# All NBA routers use the same /api/nba prefix - they have their own sub-prefixes internally
app.include_router(nba_predictions.router, prefix="/api/nba")
app.include_router(nba_players.router, prefix="/api/nba")
app.include_router(nba_data.router, prefix="/api/nba")
app.include_router(nba_odds.router, prefix="/api/nba")
app.include_router(nba_injuries.router, prefix="/api/nba")
app.include_router(nba_lineups.router, prefix="/api/nba")
app.include_router(nba_parlays.router, prefix="/api/nba")
app.include_router(nba_historical_odds.router, prefix="/api/nba")
app.include_router(nba_opening_odds.router, prefix="/api/nba")
app.include_router(nba_minutes_projection.router, prefix="/api/nba")
# NFL routes
app.include_router(nfl_predictions.router, prefix="/api/nfl")
# Shared routes (sport-agnostic) - these keep their own prefixes
app.include_router(accuracy.router)
app.include_router(bets.router)
app.include_router(parlays_router)  # New shared parlays routes
app.include_router(sync.router)  # Data sync layer
app.include_router(admin_deploy.router)  # Admin deployment routes


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "sports": ["nba", "nfl"],
        "endpoints": {
            "nba": {
                "predictions": "/api/nba/predictions",
                "players": "/api/nba/players",
                "data": "/api/nba/data",
                "odds": "/api/nba/odds",
                "injuries": "/api/nba/injuries",
                "lineups": "/api/nba/lineups",
                "parlays": "/api/nba/parlays",
                "historical_odds": "/api/nba/historical-odds"
            },
            "nfl": {
                "predictions": "/api/nfl/api/nfl/predictions"
            },
            "shared": {
                "accuracy": "/api/accuracy",
                "bets": "/api/bets",
                "parlays": "/api/parlays"
            },
            "admin": {
                "deploy": "/api/admin/deploy/deploy",
                "status": "/api/admin/deploy/status",
                "webhook": "/api/admin/deploy/webhook"
            },
            "docs": "/docs",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION
    }


@app.get("/api/health")
async def api_health():
    """Detailed API health check."""
    try:
        from app.core.database import SessionLocal
        from app.models.nba.models import Player, Game, Prediction, PlayerInjury, ExpectedLineup

        db = SessionLocal()

        # Check database connectivity and counts
        player_count = db.query(Player).count()
        game_count = db.query(Game).count()
        prediction_count = db.query(Prediction).count()
        injury_count = db.query(PlayerInjury).count()
        lineup_count = db.query(ExpectedLineup).count()

        # Import here to avoid circular dependency
        from app.models.nba.models import HistoricalOddsSnapshot

        historical_odds_count = db.query(HistoricalOddsSnapshot).count()
        resolved_odds_count = db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.hit_result.isnot(None)
        ).count()

        db.close()

        return {
            "status": "healthy",
            "version": settings.APP_VERSION,
            "database": {
                "status": "connected",
                "players": player_count,
                "games": game_count,
                "predictions": prediction_count,
                "injuries": injury_count,
                "lineups": lineup_count,
                "historical_odds_snapshots": historical_odds_count,
                "historical_odds_resolved": resolved_odds_count
            },
            "endpoints": {
                "nba": {
                    "predictions": "/api/nba/predictions",
                    "players": "/api/nba/players",
                    "data": "/api/nba/data",
                    "odds": "/api/nba/odds",
                    "injuries": "/api/nba/injuries",
                    "lineups": "/api/nba/lineups",
                    "parlays": "/api/nba/parlays",
                    "historical_odds": "/api/nba/historical-odds"
                },
                "shared": {
                    "accuracy": "/api/accuracy",
                    "bets": "/api/bets"
                }
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
