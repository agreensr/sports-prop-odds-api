"""
Main FastAPI application for NBA Player Prop Prediction API.
"""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.database import init_db
from app.core.logging import configure_logging, get_logger
from app.core.middleware import CorrelationIdMiddleware
from app.core import metrics
# Distributed tracing
from app.core.tracing import (
    init_tracing,
    add_span_attributes,
    record_exception
)
# Sport-specific routes
from app.api.routes.nba import predictions as nba_predictions, players as nba_players, data as nba_data, odds as nba_odds, injuries as nba_injuries, lineups as nba_lineups, parlays as nba_parlays, historical_odds as nba_historical_odds, opening_odds as nba_opening_odds, minutes_projection as nba_minutes_projection
from app.api.routes.nfl import predictions as nfl_predictions
# Shared routes
from app.api.routes.shared import accuracy, bets, single_bets
from app.api.routes import sync
from app.api.routes.parlays import router as parlays_router
from app.api.routes import parlays_v2  # Phase 4: Enhanced 2-leg parlays
# Admin routes
from app.api.routes.admin import deploy as admin_deploy

# Load environment variables from .env file
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configure structured logging with JSON formatter
configure_logging(
    level=settings.LOG_LEVEL,
    json_output=True  # Set to False for development for colored output
)
logger = get_logger(__name__)

# Configure rate limiting
def get_rate_limit_key(request: Request) -> str:
    """
    Get the rate limit key for a request.

    Uses IP address, with fallback to X-Forwarded-For for proxied requests.
    """
    # Check for forwarded address (behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


# Initialize limiter - will be configured after app creation
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=["60/minute"],  # General limit for most endpoints
    storage_uri=settings.REDIS_URL if settings.RATE_LIMIT_STORAGE == "redis" else "memory://",
    enabled=settings.RATE_LIMIT_ENABLED
)


# Rate limiting decorators for use in other modules
def rate_limit_predictions(endpoint_func):
    """Decorator to apply 10/minute rate limit for prediction endpoints."""
    return limiter.limit("10/minute")(endpoint_func)


def rate_limit_general(endpoint_func):
    """Decorator to apply 60/minute rate limit for general endpoints."""
    return limiter.limit("60/minute")(endpoint_func)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Initialize distributed tracing (before other instrumentation)
    # This enables tracing for FastAPI, SQLAlchemy, and HTTP clients
    try:
        init_tracing(
            service_name=settings.APP_NAME,
            environment=settings.ENVIRONMENT,
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
            console_export=settings.DEBUG,  # Console export in development
            sampling_ratio=float(os.getenv("OTEL_SAMPLING_RATIO", "0.1")),  # 10% in production
        )
    except Exception as e:
        logger.warning(f"Failed to initialize tracing: {e}")

    # Start the automation scheduler
    from app.core.scheduler import start_scheduler
    await start_scheduler()
    logger.info("Automation scheduler started")

    # Update scheduler metrics
    metrics.update_scheduler_metrics()

    # Skip init_db() for existing databases - tables already exist
    # init_db()
    logger.info("Application started")

    yield

    # Shutdown
    from app.core.scheduler import stop_scheduler
    await stop_scheduler()
    logger.info("Automation scheduler stopped")
    logger.info("Shutting down application")


# Create FastAPI app with rate limiting
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-powered player prop predictions for NBA, NFL, and more with official league API integration",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add correlation ID middleware (must be added before CORS for proper header handling)
app.add_middleware(CorrelationIdMiddleware)

# Initialize Prometheus metrics BEFORE including routes
# This must happen before any routes are added to the app
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
logger.info("Prometheus metrics initialized at /metrics")

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
# NEVER add sport-specific features to shared routes!
# ALWAYS use fully-qualified imports: from app.api.routes.nba import ...
#
# ============================================================================

# Include routers with versioned API prefixes
# API v1 - All routes use /api/v1/ prefix for versioning
# NBA routes
app.include_router(nba_predictions.router, prefix="/api/v1/nba")
app.include_router(nba_players.router, prefix="/api/v1/nba")
app.include_router(nba_data.router, prefix="/api/v1/nba")
app.include_router(nba_odds.router, prefix="/api/v1/nba")
app.include_router(nba_injuries.router, prefix="/api/v1/nba")
app.include_router(nba_lineups.router, prefix="/api/v1/nba")
app.include_router(nba_parlays.router, prefix="/api/v1/nba")
app.include_router(nba_historical_odds.router, prefix="/api/v1/nba")
app.include_router(nba_opening_odds.router, prefix="/api/v1/nba")
app.include_router(nba_minutes_projection.router, prefix="/api/v1/nba")
# NFL routes
app.include_router(nfl_predictions.router, prefix="/api/v1/nfl")
# Shared routes (sport-agnostic) - these keep their own prefixes
app.include_router(accuracy.router, prefix="/api/v1")
app.include_router(bets.router, prefix="/api/v1")
app.include_router(single_bets.router, prefix="/api/v1")  # Single bets API
app.include_router(parlays_router, prefix="/api/v1")  # Original parlays routes
app.include_router(parlays_v2.router, prefix="/api/v1")  # Phase 4: Enhanced 2-leg parlays
app.include_router(sync.router, prefix="/api/v1")  # Data sync layer
# Admin routes - not versioned (admin tools don't follow API versioning)
app.include_router(admin_deploy.router, prefix="/api/admin")  # Admin deployment routes


@app.get("/")
@limiter.limit("60/minute")
async def root(request: Request):
    """Root endpoint with API information."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "sports": ["nba", "nfl"],
        "endpoints": {
            "api_version": "v1",
            "nba": {
                "predictions": "/api/v1/nba/predictions",
                "players": "/api/v1/nba/players",
                "data": "/api/v1/nba/data",
                "odds": "/api/v1/nba/odds",
                "injuries": "/api/v1/nba/injuries",
                "lineups": "/api/v1/nba/lineups",
                "parlays": "/api/v1/nba/parlays",
                "historical_odds": "/api/v1/nba/historical-odds"
            },
            "nfl": {
                "predictions": "/api/v1/nfl/predictions"
            },
            "shared": {
                "accuracy": "/api/v1/accuracy",
                "bets": "/api/v1/bets",
                "single-bets": "/api/v1/single-bets",
                "parlays": "/api/v1/parlays",
                "parlays-v2": "/api/v1/parlays-v2"
            },
            "admin": {
                "deploy": "/api/admin/deploy",
                "status": "/api/admin/deploy/status",
                "webhook": "/api/admin/deploy/webhook"
            },
            "docs": "/docs",
            "health": "/health"
        }
    }


@app.get("/health")
@limiter.limit("120/minute")  # Higher limit for health checks
async def health_check(request: Request):
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION
    }


@app.get("/api/health")
@limiter.limit("60/minute")
async def api_health(request: Request):
    """Detailed API health check with component-level status."""
    health_status = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "components": {}
    }

    all_healthy = True

    # 1. Database Health Check
    try:
        from app.core.database import SessionLocal, engine
        from app.models import Player, Game, Prediction, PlayerInjury, ExpectedLineup
        from app.models import HistoricalOddsSnapshot

        db = SessionLocal()

        # Check database connectivity and counts
        player_count = db.query(Player).count()
        game_count = db.query(Game).count()
        prediction_count = db.query(Prediction).count()
        injury_count = db.query(PlayerInjury).count()
        lineup_count = db.query(ExpectedLineup).count()
        historical_odds_count = db.query(HistoricalOddsSnapshot).count()
        resolved_odds_count = db.query(HistoricalOddsSnapshot).filter(
            HistoricalOddsSnapshot.hit_result.isnot(None)
        ).count()

        # Database pool status
        pool = engine.pool
        db_pool_status = {
            "status": "connected",
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "counts": {
                "players": player_count,
                "games": game_count,
                "predictions": prediction_count,
                "injuries": injury_count,
                "lineups": lineup_count,
                "historical_odds_snapshots": historical_odds_count,
                "historical_odds_resolved": resolved_odds_count
            }
        }

        health_status["components"]["database"] = db_pool_status

        # Update database pool metrics
        metrics.update_db_pool_metrics()

        db.close()

    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        all_healthy = False

    # 2. Scheduler Health Check
    try:
        from app.core.scheduler import get_scheduler

        scheduler = get_scheduler()
        if scheduler and scheduler.running:
            jobs = scheduler.scheduler.get_jobs() if scheduler.scheduler else []
            health_status["components"]["scheduler"] = {
                "status": "running",
                "jobs_count": len(jobs),
                "jobs": [{"id": j.id, "name": j.name} for j in jobs]
            }
        else:
            health_status["components"]["scheduler"] = {
                "status": "stopped"
            }
            all_healthy = False

        # Update scheduler metrics
        metrics.update_scheduler_metrics()

    except Exception as e:
        logger.error(f"Scheduler health check failed: {e}")
        health_status["components"]["scheduler"] = {
            "status": "error",
            "error": str(e)
        }
        all_healthy = False

    # 3. Odds API Health Check
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Make a lightweight request to check connectivity
            params = {"apiKey": settings.ODDS_API_KEY}
            response = await client.get(
                "https://api.the-odds-api.com/v4/sports/basketball_nba/scores",
                params=params
            )

            if response.status_code == 200:
                # Check quota headers
                remaining = response.headers.get("x-requests-remaining")
                used = response.headers.get("x-requests-used")

                odds_status = {
                    "status": "connected",
                    "response_time_ms": response.elapsed.total_seconds() * 1000
                }

                if remaining:
                    odds_status["quota_remaining"] = int(remaining)
                    remaining_int = int(remaining)
                    if remaining_int < 1000:  # Less than 5%
                        odds_status["quota_status"] = "critical"
                    elif remaining_int < 4000:  # Less than 20%
                        odds_status["quota_status"] = "warning"
                    else:
                        odds_status["quota_status"] = "ok"

                if used:
                    odds_status["quota_used"] = int(used)

                health_status["components"]["odds_api"] = odds_status
            else:
                health_status["components"]["odds_api"] = {
                    "status": "error",
                    "status_code": response.status_code
                }
                all_healthy = False

    except Exception as e:
        logger.error(f"Odds API health check failed: {e}")
        health_status["components"]["odds_api"] = {
            "status": "unreachable",
            "error": str(e)
        }
        # Don't fail overall health for external API issues
        # Comment out next line if you want partial degradation
        # all_healthy = False

    # 4. ESPN API Health Check
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Make a lightweight request to check connectivity
            response = await client.get(
                "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
            )

            if response.status_code == 200:
                health_status["components"]["espn_api"] = {
                    "status": "connected",
                    "response_time_ms": response.elapsed.total_seconds() * 1000
                }
            else:
                health_status["components"]["espn_api"] = {
                    "status": "error",
                    "status_code": response.status_code
                }
                all_healthy = False

    except Exception as e:
        logger.error(f"ESPN API health check failed: {e}")
        health_status["components"]["espn_api"] = {
            "status": "unreachable",
            "error": str(e)
        }
        # Don't fail overall health for external API issues

    # Set overall status
    if not all_healthy:
        health_status["status"] = "degraded"

    # Add endpoints documentation
    health_status["endpoints"] = {
        "metrics": "/metrics",
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

    # Return appropriate status code
    status_code = 200 if health_status["status"] == "healthy" else 503

    return JSONResponse(
        status_code=status_code,
        content=health_status
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


# ============================================================================
# BACKWARD COMPATIBILITY ROUTES
# ============================================================================
# Redirect unversioned API paths to versioned paths for backward compatibility
# This ensures existing clients continue to work without breaking changes

# NBA backward compatibility redirects
@app.api_route("/api/nba/predictions", methods=["GET", "POST"])
async def nba_predictions_redirect(request: Request):
    """Redirect /api/nba/predictions to /api/v1/nba/predictions"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/predictions?{request.url.query}", status_code=301)


@app.api_route("/api/nba/players", methods=["GET"])
async def nba_players_redirect(request: Request):
    """Redirect /api/nba/players to /api/v1/nba/players"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/players?{request.url.query}", status_code=301)


@app.api_route("/api/nba/data", methods=["GET"])
async def nba_data_redirect(request: Request):
    """Redirect /api/nba/data to /api/v1/nba/data"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/data?{request.url.query}", status_code=301)


@app.api_route("/api/nba/odds", methods=["GET"])
async def nba_odds_redirect(request: Request):
    """Redirect /api/nba/odds to /api/v1/nba/odds"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/odds?{request.url.query}", status_code=301)


@app.api_route("/api/nba/injuries", methods=["GET"])
async def nba_injuries_redirect(request: Request):
    """Redirect /api/nba/injuries to /api/v1/nba/injuries"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/injuries?{request.url.query}", status_code=301)


@app.api_route("/api/nba/lineups", methods=["GET"])
async def nba_lineups_redirect(request: Request):
    """Redirect /api/nba/lineups to /api/v1/nba/lineups"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/lineups?{request.url.query}", status_code=301)


@app.api_route("/api/nba/parlays", methods=["GET", "POST"])
async def nba_parlays_redirect(request: Request):
    """Redirect /api/nba/parlays to /api/v1/nba/parlays"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/parlays?{request.url.query}", status_code=301)


@app.api_route("/api/nba/historical-odds", methods=["GET", "POST"])
async def nba_historical_odds_redirect(request: Request):
    """Redirect /api/nba/historical-odds to /api/v1/nba/historical-odds"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/historical-odds?{request.url.query}", status_code=301)


@app.api_route("/api/nba/opening-odds", methods=["GET", "POST"])
async def nba_opening_odds_redirect(request: Request):
    """Redirect /api/nba/opening-odds to /api/v1/nba/opening-odds"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/opening-odds?{request.url.query}", status_code=301)


@app.api_route("/api/nba/minutes-projection", methods=["GET"])
async def nba_minutes_projection_redirect(request: Request):
    """Redirect /api/nba/minutes-projection to /api/v1/nba/minutes-projection"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nba/minutes-projection?{request.url.query}", status_code=301)


# NFL backward compatibility redirects
@app.api_route("/api/nfl/predictions", methods=["GET", "POST"])
async def nfl_predictions_redirect(request: Request):
    """Redirect /api/nfl/predictions to /api/v1/nfl/predictions"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/nfl/predictions?{request.url.query}", status_code=301)


# Shared routes backward compatibility redirects
@app.api_route("/api/accuracy", methods=["GET", "POST"])
async def accuracy_redirect(request: Request):
    """Redirect /api/accuracy to /api/v1/accuracy"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/accuracy?{request.url.query}", status_code=301)


@app.api_route("/api/bets", methods=["GET", "POST", "PUT", "DELETE"])
async def bets_redirect(request: Request):
    """Redirect /api/bets to /api/v1/bets"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/bets?{request.url.query}", status_code=301)


@app.api_route("/api/single-bets", methods=["GET", "POST"])
async def single_bets_redirect(request: Request):
    """Redirect /api/single-bets to /api/v1/single-bets"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/single-bets?{request.url.query}", status_code=301)


@app.api_route("/api/parlays", methods=["GET", "POST"])
async def parlays_redirect(request: Request):
    """Redirect /api/parlays to /api/v1/parlays"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/parlays?{request.url.query}", status_code=301)


@app.api_route("/api/parlays-v2", methods=["GET", "POST"])
async def parlays_v2_redirect(request: Request):
    """Redirect /api/parlays-v2 to /api/v1/parlays-v2"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/parlays-v2?{request.url.query}", status_code=301)


@app.api_route("/api/sync", methods=["GET", "POST"])
async def sync_redirect(request: Request):
    """Redirect /api/sync to /api/v1/sync"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=f"/api/v1/sync?{request.url.query}", status_code=301)


# ============================================================================
# END BACKWARD COMPATIBILITY ROUTES
# ============================================================================


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
