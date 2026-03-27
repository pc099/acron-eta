"""Sentry context middleware - adds org_id, agent_id, request_id to every error.

Enriches Sentry errors with request-specific context for easier debugging.
"""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SentryContextMiddleware(BaseHTTPMiddleware):
    """Add request context to Sentry scope for all errors."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Set Sentry context from request state before processing.

        Args:
            request: FastAPI request
            call_next: Next middleware in chain

        Returns:
            Response from downstream handlers
        """
        try:
            import sentry_sdk
        except ImportError:
            # Sentry not installed or initialized
            return await call_next(request)

        # Set context from request state (populated by AuthMiddleware, RequestIDMiddleware, etc.)
        with sentry_sdk.push_scope() as scope:
            # Organization context
            if hasattr(request.state, "org_id"):
                scope.set_tag("org_id", request.state.org_id)
                scope.set_context("organization", {"id": request.state.org_id})

            # Agent context (if available)
            if hasattr(request.state, "agent_id"):
                scope.set_tag("agent_id", request.state.agent_id)
                scope.set_context("agent", {"id": request.state.agent_id})

            # Request ID for correlation
            if hasattr(request.state, "request_id"):
                scope.set_tag("request_id", request.state.request_id)
                scope.set_context("request", {"id": request.state.request_id})

            # HTTP request details
            scope.set_tag("method", request.method)
            scope.set_tag("path", request.url.path)

            # User context (if available from auth)
            if hasattr(request.state, "user_id"):
                scope.set_user({"id": request.state.user_id})

            response = await call_next(request)
            return response
