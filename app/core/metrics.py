"""
Prometheus metrics for sports-bet-ai-api.

This module defines all Prometheus metrics used for monitoring and observability.

Metrics exposed:
- HTTP request counters and latency histograms
- External API success/failure counters
- API quota monitoring gauges
- Database connection pool gauges
- Scheduler status gauge
"""
from prometheus_client import Counter, Gauge, Histogram

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"]
)

# External API Metrics
odds_api_requests_success_total = Counter(
    "odds_api_requests_success_total",
    "Total successful Odds API requests"
)

odds_api_requests_failure_total = Counter(
    "odds_api_requests_failure_total",
    "Total failed Odds API requests",
    ["error_type"]
)

espn_api_requests_success_total = Counter(
    "espn_api_requests_success_total",
    "Total successful ESPN API requests"
)

espn_api_requests_failure_total = Counter(
    "espn_api_requests_failure_total",
    "Total failed ESPN API requests",
    ["error_type"]
)

# API Quota Metrics
odds_api_quota_remaining = Gauge(
    "odds_api_quota_remaining",
    "Remaining Odds API requests for current billing period"
)

odds_api_quota_used = Gauge(
    "odds_api_quota_used",
    "Used Odds API requests in current billing period"
)

odds_api_quota_percentage = Gauge(
    "odds_api_quota_percentage",
    "Percentage of Odds API quota used"
)

# Database Metrics
db_pool_connections = Gauge(
    "db_pool_connections",
    "Number of database connections in the pool"
)

db_pool_connections_idle = Gauge(
    "db_pool_connections_idle",
    "Number of idle database connections"
)

db_pool_connections_checked_out = Gauge(
    "db_pool_connections_checked_out",
    "Number of checked out database connections"
)

db_pool_connections_overflow = Gauge(
    "db_pool_connections_overflow",
    "Number of overflow database connections"
)

db_pool_connections_invalid = Gauge(
    "db_pool_connections_invalid",
    "Number of invalid database connections"
)

# Scheduler Metrics
scheduler_running = Gauge(
    "scheduler_running",
    "Whether the automation scheduler is running (1=running, 0=stopped)"
)

scheduler_jobs_total = Gauge(
    "scheduler_jobs_total",
    "Total number of scheduled jobs"
)

# Prediction Metrics
predictions_generated_total = Counter(
    "predictions_generated_total",
    "Total predictions generated",
    ["sport"]
)

prediction_errors_total = Counter(
    "prediction_errors_total",
    "Total prediction generation errors",
    ["sport", "error_type"]
)

# Circuit Breaker Metrics
circuit_breaker_state = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["service"]
)

circuit_breaker_failures_total = Counter(
    "circuit_breaker_failures_total",
    "Total circuit breaker failures",
    ["service"]
)


def update_db_pool_metrics():
    """
    Update database connection pool metrics from SQLAlchemy engine.

    Call this periodically to update pool metrics.
    """
    from app.core.database import engine

    pool = engine.pool
    if pool:
        db_pool_connections.set(pool.size())
        db_pool_connections_idle.set(pool.checkedin())
        db_pool_connections_checked_out.set(pool.checkedout())

        # Additional pool metrics
        db_pool_connections_overflow.set(pool.overflow())
        # Invalid connections may not be available in all pool implementations
        try:
            db_pool_connections_invalid.set(pool.invalid())
        except AttributeError:
            pass


def update_scheduler_metrics():
    """
    Update scheduler metrics.

    Call this periodically to update scheduler status.
    """
    from app.core.scheduler import get_scheduler

    scheduler = get_scheduler()
    if scheduler and scheduler.running:
        scheduler_running.set(1)
        if scheduler.scheduler:
            scheduler_jobs_total.set(len(scheduler.scheduler.get_jobs()))
    else:
        scheduler_running.set(0)
        scheduler_jobs_total.set(0)


def update_odds_api_quota(remaining: int, used: int, monthly_quota: int = 20000):
    """
    Update Odds API quota metrics.

    Args:
        remaining: Remaining requests
        used: Used requests
        monthly_quota: Monthly quota (default: 20000)
    """
    odds_api_quota_remaining.set(remaining)
    odds_api_quota_used.set(used)

    if used > 0 and monthly_quota > 0:
        percentage = (used / monthly_quota) * 100
        odds_api_quota_percentage.set(percentage)
    else:
        odds_api_quota_percentage.set(0)


def record_odds_api_request_success():
    """Record a successful Odds API request."""
    odds_api_requests_success_total.inc()


def record_odds_api_request_failure(error_type: str = "unknown"):
    """Record a failed Odds API request."""
    odds_api_requests_failure_total.labels(error_type=error_type).inc()


def record_espn_api_request_success():
    """Record a successful ESPN API request."""
    espn_api_requests_success_total.inc()


def record_espn_api_request_failure(error_type: str = "unknown"):
    """Record a failed ESPN API request."""
    espn_api_requests_failure_total.labels(error_type=error_type).inc()
