"""
Structured logging module with JSON formatting and correlation ID support.

This module provides:
- JSON log formatting for structured logging
- Correlation ID tracking via context variables
- Logger factory for consistent logger creation
"""
import logging
import json
import sys
from datetime import datetime
from typing import Any
from contextvars import ContextVar

# Context variable for correlation ID - shared across the application
# This allows the correlation ID to be accessed in any log call
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Outputs logs as JSON objects with the following fields:
    - timestamp: ISO 8601 formatted timestamp
    - level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - logger: Logger name
    - message: Log message
    - correlation_id: Request correlation ID (if available)
    - exception: Exception details (if an exception occurred)
    - extra: Any additional context from extra dict
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Build base log data
        log_data: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add any extra fields from the record
        # Skip standard attributes and those already included
        extra_keys = {
            k: v
            for k, v in record.__dict__.items()
            if k
            not in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "asctime",
            }
        }
        if extra_keys:
            log_data["extra"] = extra_keys

        return json.dumps(log_data)


class ColoredFormatter(logging.Formatter):
    """
    Colored console formatter for development.

    Provides human-readable colored output for console logging
    while still including correlation IDs.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        level_color = self.COLORS.get(record.levelname, "")
        correlation_id = correlation_id_var.get()

        base_msg = f"{level_color}[{record.levelname}]{self.RESET} {record.name}: {record.getMessage()}"

        if correlation_id:
            base_msg += f" | correlation_id={correlation_id}"

        if record.exc_info:
            base_msg += "\n" + self.formatException(record.exc_info)

        return base_msg


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    handler: logging.Handler | None = None,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, use JSON formatter. If False, use colored console formatter.
        handler: Optional custom handler. If None, creates StreamHandler to stdout.
    """
    # Clear any existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Set log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Create handler if not provided
    if handler is None:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)

    # Choose formatter
    if json_output:
        formatter = JSONFormatter()
    else:
        formatter = ColoredFormatter()

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Reduce noise from third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name (typically __name__ from the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def set_correlation_id(correlation_id: str) -> Any:
    """
    Set the correlation ID in the context.

    Args:
        correlation_id: The correlation ID to set

    Returns:
        Token that can be used to reset the context variable
    """
    return correlation_id_var.set(correlation_id)


def get_correlation_id() -> str:
    """
    Get the current correlation ID from the context.

    Returns:
        Current correlation ID or empty string if not set
    """
    return correlation_id_var.get()


def clear_correlation_id(token: Any) -> None:
    """
    Clear the correlation ID from the context.

    Args:
        token: The token returned by set_correlation_id
    """
    correlation_id_var.reset(token)
