"""
Distributed tracing configuration using OpenTelemetry.

Provides automatic instrumentation for:
- FastAPI endpoints
- SQLAlchemy database queries
- HTTP client requests (httpx)
- Custom spans for business logic

Exports traces to:
- Console (development)
- OTLP endpoint (production - Jaeger, Tempo, etc.)

Usage:
    from app.core.tracing import init_tracing

    # Initialize with config
    init_tracing(
        service_name="sports-bet-ai-api",
        environment="development",
        otlp_endpoint=None  # Set to Jaeger/Tempo endpoint in production
    )
"""
import os
import logging
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Configuration from environment
OTEL_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "sports-bet-ai-api")
OTEL_ENVIRONMENT = os.getenv("OTEL_ENVIRONMENT", "development")
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")  # e.g., http://jaeger:4317
OTEL_EXPORTER_CONSOLE = os.getenv("OTEL_EXPORTER_CONSOLE", "true").lower() == "true"
OTEL_SAMPLING_RATIO = float(os.getenv("OTEL_SAMPLING_RATIO", "1.0"))  # 1.0 = trace everything
OTEL_TRACES_ENABLED = os.getenv("OTEL_TRACES_ENABLED", "true").lower() == "true"

# Global tracing state
_tracing_initialized = False


def init_tracing(
    service_name: str = OTEL_SERVICE_NAME,
    environment: str = OTEL_ENVIRONMENT,
    otlp_endpoint: Optional[str] = None,
    console_export: bool = True,
    sampling_ratio: float = 1.0,
    sqlalchemy_instrument: bool = True,
    httpx_instrument: bool = True
) -> None:
    """
    Initialize OpenTelemetry distributed tracing.

    Args:
        service_name: Name of this service (for trace identification)
        environment: Environment (development, staging, production)
        otlp_endpoint: OTLP endpoint (Jaeger, Tempo, etc.)
        console_export: Export spans to console (useful for development)
        sampling_ratio: Fraction of traces to sample (0.0 to 1.0)
        sqlalchemy_instrument: Auto-instrument SQLAlchemy queries
        httpx_instrument: Auto-instrument HTTP client requests

    Example:
        # Development - console only
        init_tracing()

        # Production - OTLP exporter
        init_tracing(
            otlp_endpoint="http://jaeger:4317",
            console_export=False,
            sampling_ratio=0.1  # 10% sampling
        )
    """
    global _tracing_initialized

    if _tracing_initialized:
        logger.warning("Tracing already initialized, skipping")
        return

    if not OTEL_TRACES_ENABLED:
        logger.info("OpenTelemetry tracing disabled via OTEL_TRACES_ENABLED")
        return

    # Import OpenTelemetry packages
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, OTEL_SCHEMA_URL
        from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
        from opentelemetry import propagate
    except ImportError as e:
        logger.warning(f"OpenTelemetry not available, tracing disabled: {e}")
        logger.debug("Install with: pip install opentelemetry-api opentelemetry-sdk "
                     "opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy")
        return

    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: service_name,
        "deployment.environment": environment,
        "service.version": os.getenv("APP_VERSION", "1.0.0"),
    })

    # Configure tracer provider
    tracer_provider = TracerProvider(resource=resource)

    # Sampling configuration
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    sampler = TraceIdRatioBased(sampling_ratio)
    tracer_provider = TracerProvider(resource=resource, sampler=sampler)

    # Add exporters
    exporters_added = 0

    # Console exporter (development)
    if console_export or OTEL_EXPORTER_CONSOLE:
        console_exporter = ConsoleSpanExporter()
        tracer_provider.add_span_processor(BatchSpanProcessor(console_exporter))
        exporters_added += 1
        logger.debug("Added console span exporter")

    # OTLP exporter (production)
    endpoint = otlp_endpoint or OTEL_EXPORTER_OTLP_ENDPOINT
    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            exporters_added += 1
            logger.info(f"Added OTLP span exporter: {endpoint}")
        except ImportError:
            logger.warning("OTLP exporter not available, install: pip install opentelemetry-exporter-otlp")

    if exporters_added == 0:
        logger.warning("No span exporters configured, traces will not be exported")

    # Set global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Set global propagator (for distributed tracing)
    propagate.set_global_textmap(TraceContextTextMapPropagator())
    logger.debug("Set global trace propagator: TraceContextTextMapPropagator")

    # Auto-instrumentation
    instrument_fastapi(tracer_provider)
    if sqlalchemy_instrument:
        instrument_sqlalchemy(tracer_provider)
    if httpx_instrument:
        instrument_httpx(tracer_provider)

    _tracing_initialized = True
    logger.info(f"OpenTelemetry tracing initialized: service={service_name}, env={environment}")


def instrument_fastapi(tracer_provider) -> None:
    """Instrument FastAPI for automatic span creation."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider

        # Ensure we have the right provider type
        if not isinstance(tracer_provider, TracerProvider):
            logger.warning("Unexpected tracer provider type for FastAPI instrumentation")
            return

        # Check if FastAPI is already instrumented
        if FastAPIInstrumentor().is_instrumented_by_opentelemetry:
            logger.debug("FastAPI already instrumented")
            return

        FastAPIInstrumentor().instrument_app(
            tracer_provider=tracer_provider,
            # Exclude specific endpoints from tracing
            excluded_urls=[
                "/health",  # Health checks are noisy
                "/metrics",  # Prometheus scraping is high-frequency
                "/docs",     # Swagger UI
                "/openapi.json",
            ],
            # Add custom attributes to request spans
            span_details={
                "http.query": True,
                "http.route": True,
            }
        )
        logger.info("Instrumented FastAPI")
    except ImportError:
        logger.warning("FastAPI instrumentation not available")
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")


def instrument_sqlalchemy(tracer_provider) -> None:
    """Instrument SQLAlchemy for automatic database query spans."""
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(
            tracer_provider=tracer_provider,
            # Enable commenter for query comments (shows what code triggered query)
            enable_commenter=True,
            # Capture connection details
            capture_connection=True,
            # Capture table details
            capture_table_name=True,
        )
        logger.info("Instrumented SQLAlchemy")
    except ImportError:
        logger.warning("SQLAlchemy instrumentation not available")
    except Exception as e:
        logger.error(f"Failed to instrument SQLAlchemy: {e}")


def instrument_httpx(tracer_provider) -> None:
    """Instrument httpx for HTTP client tracing."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(
            tracer_provider=tracer_provider,
            # Capture request headers (be careful with sensitive data)
            capture_request_headers=False,
            # Capture response headers
            capture_response_headers=False,
        )
        logger.info("Instrumented httpx")
    except ImportError:
        logger.warning("httpx instrumentation not available")
    except Exception as e:
        logger.error(f"Failed to instrument httpx: {e}")


def get_tracer(name: str):
    """
    Get a tracer for manual span creation.

    Use for custom spans in business logic.

    Args:
        name: Name of the tracer/module (e.g., "app.services.nba")

    Returns:
        Tracer instance

    Example:
        from app.core.tracing import get_tracer

        tracer = get_tracer("app.services.nba")
        with tracer.start_as_current_span("generate_predictions"):
            # Your code here
            pass
    """
    from opentelemetry import trace
    return trace.get_tracer(name)


@contextmanager
def span(name: str, attributes: Optional[dict] = None):
    """
    Context manager for creating custom spans.

    Simplifies manual span creation in business logic.

    Args:
        name: Span name (describe the operation)
        attributes: Key-value pairs to attach to the span

    Example:
        from app.core.tracing import span

        with span("fetch_player_stats", {"player_id": "123", "source": "espn"}):
            stats = fetch_stats(player_id)
    """
    from opentelemetry import trace

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name, attributes=attributes) as s:
        yield s


def add_span_attributes(**attributes) -> None:
    """
    Add attributes to the current span.

    Useful for adding dynamic context to auto-generated spans.

    Args:
        **attributes: Key-value pairs to add to the span

    Example:
        from app.core.tracing import add_span_attributes

        add_span_attributes(
            player_id="123",
            team="BOS",
            prediction_confidence=0.85
        )
    """
    from opentelemetry import trace
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.set_attributes(attributes)


def add_span_event(name: str, attributes: Optional[dict] = None) -> None:
    """
    Add an event to the current span.

    Events are timestamped annotations within a span.

    Args:
        name: Event name
        attributes: Key-value pairs describing the event

    Example:
        from app.core.tracing import add_span_event

        add_span_event("cache_hit", {"key": "player:123:stats"})
    """
    from opentelemetry import trace
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.add_event(name, attributes=attributes)


def record_exception(exception: Exception, attributes: Optional[dict] = None) -> None:
    """
    Record an exception on the current span.

    Marks the span as having an error and captures exception details.

    Args:
        exception: The exception to record
        attributes: Additional context about the exception

    Example:
        from app.core.tracing import record_exception
        try:
            risky_operation()
        except ValueError as e:
            record_exception(e, {"operation": "risky_operation"})
            raise
    """
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode

    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        current_span.record_exception(exception)
        current_span.set_status(
            Status(StatusCode.ERROR, str(exception))
        )
        if attributes:
            current_span.set_attributes(attributes)


def get_trace_id() -> Optional[str]:
    """
    Get the current trace ID.

    Useful for logging correlation - include this ID in log messages
    to find related traces.

    Returns:
        Trace ID as hex string, or None if no active trace

    Example:
        from app.core.tracing import get_trace_id
        import logging

        logger.info("Processing request", extra={"trace_id": get_trace_id()})
    """
    from opentelemetry import trace
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_context = current_span.get_span_context()
        if span_context and span_context.trace_id:
            return format(span_context.trace_id, "032x")
    return None


def get_span_id() -> Optional[str]:
    """
    Get the current span ID.

    Returns:
        Span ID as hex string, or None if no active span
    """
    from opentelemetry import trace
    current_span = trace.get_current_span()
    if current_span and current_span.is_recording():
        span_context = current_span.get_span_context()
        if span_context and span_context.span_id:
            return format(span_context.span_id, "016x")
    return None


# =============================================================================
# Decorators for common patterns
# =============================================================================

def traced_operation(operation_name: Optional[str] = None):
    """
    Decorator to trace a function or method.

    Args:
        operation_name: Name for the span (defaults to function name)

    Example:
        from app.core.tracing import traced_operation

        @traced_operation("fetch_espn_data")
        def fetch_player_data(player_id: str):
            return fetch_from_espn(player_id)
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from opentelemetry import trace

            name = operation_name or f"{func.__module__}.{func.__name__}"
            tracer = trace.get_tracer(__name__)

            with tracer.start_as_current_span(name) as span:
                # Add function name as attribute
                span.set_attribute("code.function", func.__name__)
                span.set_attribute("code.module", func.__module__)

                # Try to get self for methods
                if args and hasattr(args[0], "__class__"):
                    span.set_attribute("code.class", args[0].__class__.__name__)

                try:
                    result = func(*args, **kwargs)
                    return result
                except Exception as e:
                    record_exception(e, {"function": func.__name__})
                    raise

        return wrapper
    return decorator


def async_traced_operation(operation_name: Optional[str] = None):
    """
    Decorator to trace an async function or method.

    Args:
        operation_name: Name for the span (defaults to function name)

    Example:
        from app.core.tracing import async_traced_operation

        @async_traced_operation("fetch_external_api")
        async def fetch_odds_api_data(game_id: str):
            return await httpx.get(f"/odds/{game_id}")
    """
    def decorator(func):
        import functools

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            from opentelemetry import trace

            name = operation_name or f"{func.__module__}.{func.__name__}"
            tracer = trace.get_tracer(__name__)

            with tracer.start_as_current_span(name) as span:
                span.set_attribute("code.function", func.__name__)
                span.set_attribute("code.module", func.__module__)
                span.set_attribute("code.async", True)

                if args and hasattr(args[0], "__class__"):
                    span.set_attribute("code.class", args[0].__class__.__name__)

                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    record_exception(e, {"function": func.__name__})
                    raise

        return wrapper
    return decorator


# =============================================================================
# Logging integration
# =============================================================================

class TraceIdFilter(logging.Filter):
    """
    Logging filter that adds trace ID to log records.

    Add to your logging configuration to correlate logs with traces.

    Example:
        import logging
        from app.core.tracing import TraceIdFilter

        logger = logging.getLogger(__name__)
        logger.addFilter(TraceIdFilter())
    """

    def filter(self, record):
        trace_id = get_trace_id()
        if trace_id:
            record.trace_id = trace_id
        span_id = get_span_id()
        if span_id:
            record.span_id = span_id
        return True


# =============================================================================
# FastAPI dependency for trace propagation
# =============================================================================

from fastapi import Header

async def get_trace_context(
    traceparent: Optional[str] = Header(None, alias="traceparent"),
    tracestate: Optional[str] = Header(None, alias="tracestate")
) -> dict:
    """
    FastAPI dependency to extract W3C trace context from incoming headers.

    Use in your endpoints to access trace information.

    Example:
        from app.core.tracing import get_trace_context

        @app.get("/api/example")
        async def example(trace: dict = Depends(get_trace_context)):
            return {"trace_id": trace.get("trace_id")}
    """
    from opentelemetry import trace
    from opentelemetry.propagators.textmap import TextMapPropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    # Extract trace context from headers
    headers = {}
    if traceparent:
        headers["traceparent"] = traceparent
    if tracestate:
        headers["tracestate"] = tracestate

    ctx = TraceContextTextMapPropagator().extract(headers)

    # Get trace info from context
    return {
        "traceparent": traceparent,
        "tracestate": tracestate,
        "trace_id": get_trace_id(),
        "span_id": get_span_id(),
    }
