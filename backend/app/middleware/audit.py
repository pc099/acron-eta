"""Audit logging middleware — writes an AuditLog entry for every API request.

Fires as a background task after the response is sent so it never
adds latency to the critical path. Skips health, docs, and OPTIONS.
"""

import logging
import uuid
from typing import Optional

from fastapi import Request
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.db.engine import async_session_factory
from app.db.models import AuditLog

logger = logging.getLogger(__name__)

_SKIP_PREFIXES = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class AuditMiddleware(BaseHTTPMiddleware):
    """Log every authenticated API request to the immutable audit log."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        response = await call_next(request)

        # Only audit authenticated requests (org_id is set by AuthMiddleware)
        org_id = getattr(request.state, "org_id", None)
        if org_id:
            response.background = BackgroundTask(
                _write_audit_entry,
                org_id=org_id,
                user_id=getattr(request.state, "user_id", None),
                method=request.method,
                path=path,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
                auth_type=getattr(request.state, "auth_type", None),
            )

        return response


async def _write_audit_entry(
    *,
    org_id: str,
    user_id: Optional[str],
    method: str,
    path: str,
    status_code: int,
    ip_address: Optional[str],
    user_agent: Optional[str],
    auth_type: Optional[str],
) -> None:
    """Insert an immutable audit log entry in its own DB session."""
    try:
        async with async_session_factory() as session:
            entry = AuditLog(
                id=uuid.uuid4(),
                organisation_id=uuid.UUID(org_id),
                user_id=uuid.UUID(user_id) if user_id else None,
                action=f"{method} {path}",
                resource_type="http_request",
                metadata_={
                    "status_code": status_code,
                    "auth_type": auth_type,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(entry)
            await session.commit()
    except Exception:
        logger.exception("Failed to write audit log for org %s", org_id)
