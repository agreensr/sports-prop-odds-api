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
from app.api.routes import predictions, players, data, odds, nfl, accuracy, parlays, bets, injuries, lineups

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
    # Skip init_db() for existing databases - tables already exist
    # init_db()
    logger.info("Application started")

    yield

    # Shutdown
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

# Include routers
app.include_router(predictions.router)
app.include_router(players.router)
app.include_router(data.router)
app.include_router(odds.router)
app.include_router(nfl.router)
app.include_router(accuracy.router)
app.include_router(parlays.router)
app.include_router(bets.router)
app.include_router(injuries.router)
app.include_router(lineups.router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "endpoints": {
            "predictions": "/api/predictions",
            "players": "/api/players",
            "data": "/api/data",
            "odds": "/api/odds",
            "accuracy": "/api/accuracy",
            "parlays": "/api/parlays",
            "bets": "/api/bets",
            "injuries": "/api/injuries",
            "lineups": "/api/lineups",
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
        from app.models.models import Player, Game, Prediction, PlayerInjury, ExpectedLineup

        db = SessionLocal()

        # Check database connectivity and counts
        player_count = db.query(Player).count()
        game_count = db.query(Game).count()
        prediction_count = db.query(Prediction).count()
        injury_count = db.query(PlayerInjury).count()
        lineup_count = db.query(ExpectedLineup).count()

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
                "lineups": lineup_count
            },
            "endpoints": {
                "predictions": "/api/predictions",
                "players": "/api/players",
                "data": "/api/data",
                "odds": "/api/odds",
                "accuracy": "/api/accuracy",
                "parlays": "/api/parlays",
                "bets": "/api/bets",
                "injuries": "/api/injuries",
                "lineups": "/api/lineups"
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
