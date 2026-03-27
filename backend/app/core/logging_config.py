"""Structured JSON logging configuration for ASAHIO platform.

All logs are output as JSON with consistent fields for searchability and filtering.
Integrates with Railway logs, Better Stack, and other log aggregation systems.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON formatter with contextual fields for platform observability."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with consistent structure.

        Standard fields:
        - timestamp: ISO 8601 UTC timestamp
        - level: Log level (INFO, WARNING, ERROR, etc.)
        - logger: Logger name (module.function)
        - message: Log message
        - module: Source module name
        - function: Source function name
        - line: Source line number

        Contextual fields (if provided via extra={}):
        - org_id: Organization UUID
        - agent_id: Agent UUID
        - request_id: Request/trace ID
        - session_id: Session UUID
        - cache_tier: exact|semantic|none
        - model_used: Model identifier
        - provider: Provider name
        - latency_ms: Request latency
        - cost_usd: Request cost
        - Any other fields passed via extra={}

        Example:
            logger.info(
                "Cache hit",
                extra={
                    "org_id": "123e4567-e89b-12d3-a456-426614174000",
                    "cache_tier": "exact",
                    "latency_ms": 5
                }
            )
        """
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add contextual fields from logger.info(..., extra={...})
        extra_fields = [
            "org_id",
            "agent_id",
            "request_id",
            "session_id",
            "cache_tier",
            "cache_hit",
            "model_used",
            "provider",
            "routing_mode",
            "intervention_mode",
            "latency_ms",
            "cost_usd",
            "risk_score",
            "bypass_cache",
            "dependency_level",
            "error",
            "skip_reason",
        ]

        for field in extra_fields:
            if hasattr(record, field):
                log_obj[field] = getattr(record, field)

        # Add exception info if present
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
            log_obj["exc_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None

        # Add stack trace for errors
        if record.levelno >= logging.ERROR and record.stack_info:
            log_obj["stack_trace"] = self.formatStack(record.stack_info)

        return json.dumps(log_obj, default=str)  # default=str handles UUID, datetime


def configure_logging(
    level: str = "INFO",
    enable_structured: bool = True,
) -> None:
    """Configure application logging with structured JSON output.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        enable_structured: If True, use JSON format. If False, use plain text.
                          Set to False for local development readability.

    Environment variables:
        LOG_LEVEL: Override level (DEBUG, INFO, WARNING, ERROR)
        STRUCTURED_LOGS: Set to "false" to disable JSON formatting
        RAILWAY_ENVIRONMENT: Auto-detected, used in log context
    """
    # Override from environment
    log_level = os.getenv("LOG_LEVEL", level).upper()
    structured_enabled = os.getenv("STRUCTURED_LOGS", "true").lower() != "false"

    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)

    # Set formatter
    if enable_structured and structured_enabled:
        formatter = StructuredFormatter()
    else:
        # Plain text for local development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    handler.setFormatter(formatter)

    # Configure root logger
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level))

    # Add Better Stack (Logtail) handler if configured
    logtail_token = os.getenv("LOGTAIL_SOURCE_TOKEN")
    if logtail_token and enable_structured and structured_enabled:
        try:
            from logtail import LogtailHandler

            logtail_handler = LogtailHandler(source_token=logtail_token)
            logtail_handler.setFormatter(StructuredFormatter())
            root_logger.addHandler(logtail_handler)
            root_logger.info("Better Stack (Logtail) log aggregation enabled")
        except ImportError:
            root_logger.warning("LOGTAIL_SOURCE_TOKEN set but logtail-python not installed")
        except Exception as exc:
            root_logger.warning("Failed to initialize Logtail handler: %s", exc)

    # Set library log levels to avoid spam
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    # Log configuration
    log_destinations = ["stdout"]
    if logtail_token:
        log_destinations.append("Better Stack")

    root_logger.info(
        "Logging configured",
        extra={
            "log_level": log_level,
            "structured": structured_enabled,
            "destinations": log_destinations,
            "environment": os.getenv("RAILWAY_ENVIRONMENT", "local"),
        }
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name.

    Usage:
        from app.core.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info("Cache hit", extra={"org_id": org_id, "cache_tier": "exact"})
    """
    return logging.getLogger(name)
