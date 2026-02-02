# Distributed Tracing with OpenTelemetry

## Overview

Distributed tracing tracks requests as they travel through the system, providing visibility into:
- End-to-end request latency
- Service dependencies and call chains
- Database query performance
- External API call timing
- Error propagation across services

## Architecture

```
Request → FastAPI (HTTP span)
           → SQLAlchemy (DB spans)
           → HTTP Client → External APIs (spans)
           → Business Logic (custom spans)
```

## Installation

```bash
# Already in requirements.txt
pip install opentelemetry-api \
            opentelemetry-sdk \
            opentelemetry-instrumentation-fastapi \
            opentelemetry-instrumentation-sqlalchemy \
            opentelemetry-instrumentation-httpx \
            opentelemetry-semantic-conventions \
            opentelemetry-exporter-otlp \
            opentelemetry-exporter-console
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OTEL_TRACES_ENABLED` | `true` | Enable/disable tracing |
| `OTEL_SERVICE_NAME` | `sports-bet-ai-api` | Service name for traces |
| `OTEL_ENVIRONMENT` | `development` | Environment (dev/staging/prod) |
| `OTEL_SAMPLING_RATIO` | `1.0` | Fraction of requests to trace (0.0-1.0) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | - | OTLP endpoint (Jaeger, Tempo) |
| `OTEL_EXPORTER_CONSOLE` | `true` | Export to console (development) |

### Examples

```bash
# Development - console export, full tracing
OTEL_TRACES_ENABLED=true
OTEL_EXPORTER_CONSOLE=true
OTEL_SAMPLING_RATIO=1.0

# Staging - OTLP export, 50% sampling
OTEL_TRACES_ENABLED=true
OTEL_ENVIRONMENT=staging
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
OTEL_SAMPLING_RATIO=0.5

# Production - OTLP export, 10% sampling
OTEL_TRACES_ENABLED=true
OTEL_ENVIRONMENT=production
OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
OTEL_SAMPLING_RATIO=0.1
```

## Usage

### Automatic Instrumentation

Traces are automatically created for:

1. **FastAPI Endpoints** - Every request gets a span
2. **SQLAlchemy Queries** - Each database query gets a span
3. **HTTPX Requests** - External API calls get spans

### Custom Spans

Add custom spans to business logic:

```python
from app.core.tracing import span

# Context manager style
with span("calculate_predictions", {"player_count": 10}):
    predictions = calculate_for_all_players()
```

### Decorator Style

```python
from app.core.tracing import traced_operation, async_traced_operation

@traced_operation("fetch_espn_data")
def fetch_from_espn(player_id: str):
    return espn_api.get_player(player_id)

@async_traced_operation("fetch_odds_api")
async def fetch_odds(game_id: str):
    return await httpx.get(f"/odds/{game_id}")
```

### Adding Attributes

```python
from app.core.tracing import add_span_attributes

# Add context to current span
add_span_attributes(
    player_id="123",
    team="BOS",
    model_version="2.0"
)
```

### Adding Events

```python
from app.core.tracing import add_span_event

# Mark specific moments in a span
add_span_event("cache_hit", {"key": "player:123"})
add_span_event("prediction_generated", {"confidence": 0.85})
```

### Recording Exceptions

```python
from app.core.tracing import record_exception

try:
    risky_operation()
except ValueError as e:
    record_exception(e, {"context": "user_input_validation"})
    raise
```

### Logging Integration

Correlate logs with traces:

```python
import logging
from app.core.tracing import TraceIdFilter, get_trace_id

# Add trace ID to log records
logger = logging.getLogger(__name__)
logger.addFilter(TraceIdFilter())

# Or manually include in logs
logger.info(f"Processing request", extra={"trace_id": get_trace_id()})
```

## Viewing Traces

### Console (Development)

Traces print to console during development:

```
{
    "name": "POST /api/v1/nba/predictions",
    "context": {
        "trace_id": "7b2c8d...",
        "span_id": "a1f3e..."
    },
    "parent": null,
    "start_time": "2024-01-15T10:30:00.123Z",
    "end_time": "2024-01-15T10:30:00.456Z",
    "attributes": {
        "http.method": "POST",
        "http.route": "/api/v1/nba/predictions",
        "http.status_code": 200
    }
}
```

### Jaeger (All-in-One)

```bash
# Run Jaeger all-in-one
docker run -d --name jaeger \
  -e COLLECTOR_OTLP_ENABLED=true \
  -p 4317:4317 \
  -p 16686:16686 \
  -p 16687:16687 \
  jaegertracing/all-in-one:latest

# Set environment variable
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# View UI at http://localhost:16686
```

### Grafana Tempo

```bash
# Run Tempo with Docker
docker-compose up -d  # Using docker-compose.tempo.yml

# Set environment variable
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
```

### Honeycomb

```bash
# Honeycomb requires Honeycomb's OpenTelemetry distro
pip install opentelemetry-exporter-otlp-proto-grpc

# Configure with Honeycomb endpoint
export OTEL_EXPORTER_OTLP_ENDPOINT=https://api.honeycomb.io:443
export HONEYCOMB_API_KEY=your-api-key
```

## Span Attributes

### Automatic Attributes

FastAPI spans include:
- `http.method` - GET, POST, etc.
- `http.route` - Route pattern
- `http.status_code` - Response status
- `http.url` - Request URL

SQLAlchemy spans include:
- `db.name` - Database name
- `db.system` - postgresql
- `db.statement` - SQL query (truncated)
- `db.operation` - SELECT, INSERT, etc.

HTTPX spans include:
- `http.method` - Request method
- `http.url` - Request URL
- `http.status_code` - Response status
- `peer.service` - External service name

### Custom Attributes

Add domain-specific attributes:

```python
from app.core.tracing import add_span_attributes

# Business context
add_span_attributes(
    sport="nba",
    player_id="1628369",
    prediction_type="points",
    model_confidence=0.85
)
```

## Sampling

In production, don't trace every request:

```python
# 10% sampling (acceptable for most services)
OTEL_SAMPLING_RATIO=0.1

# High-traffic services may need even lower
OTEL_SAMPLING_RATIO=0.01  # 1%
```

Sampling decisions are consistent for a trace - if a request is sampled, all its child spans are included.

## Performance Considerations

| Factor | Impact | Recommendation |
|--------|--------|----------------|
| Sampling ratio | Linear | Use 0.01-0.1 in production |
| Exporter choice | High | Console=slow, OTLP=fast |
| Span attributes | Linear | Keep attributes minimal |
| Batch processing | Moderate | Use BatchSpanProcessor |

## Troubleshooting

### No traces appearing

1. Check tracing is enabled:
   ```python
   echo $OTEL_TRACES_ENABLED
   ```

2. Verify packages installed:
   ```bash
   pip list | grep opentelemetry
   ```

3. Check logs for initialization errors

### Missing database spans

SQLAlchemy instrumentation requires engine initialization after tracing setup:

```python
# Correct order
init_tracing()
engine = create_engine(...)  # Must be after init_tracing()
```

### Missing HTTP client spans

Ensure httpx is imported after tracing initialization:

```python
# After app starts
import httpx
```

## Best Practices

1. **Add domain attributes** - Include sport, player_id, etc.
2. **Name spans meaningfully** - "fetch_player_stats" not "process"
3. **Use decorators for utilities** - Avoid repetitive span code
4. **Set appropriate sampling** - Balance detail vs. overhead
5. **Export to backend in prod** - Console exporter is for dev only
6. **Correlate logs** - Include trace_id in log messages

## Example Trace Flow

```
Trace: 7b2c8d...
├── POST /api/v1/nba/predictions (FastAPI)
│   ├── ├── SELECT * FROM players (SQLAlchemy)
│   │   └── Cache miss
│   ├── GET /api/espn/players/123 (HTTPX)
│   │   └── 200 OK (234ms)
│   ├── calculate_prediction (Custom)
│   │   ├── apply_injury_adjustment
│   │   └── calculate_confidence
│   └── INSERT INTO predictions (SQLAlchemy)
└── 200 OK (456ms total)
```
