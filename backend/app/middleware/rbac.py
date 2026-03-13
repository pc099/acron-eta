"""Role-based access control dependency for FastAPI endpoints.

Provides a ``require_role`` dependency that enforces a minimum role level
on JWT-authenticated requests.  API key auth bypasses RBAC (API keys use
their own scope system defined in ``auth.py``).

Usage::

    from app.middleware.rbac import require_role
    from app.db.models import MemberRole

    @router.post("/register", dependencies=[require_role(MemberRole.ADMIN)])
    async def register_endpoint(...):
        ...
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request

from app.db.models import MemberRole

logger = logging.getLogger(__name__)

# Role hierarchy — higher number = more privileged.
_ROLE_HIERARCHY: dict[MemberRole, int] = {
    MemberRole.OWNER: 4,
    MemberRole.ADMIN: 3,
    MemberRole.MEMBER: 2,
    MemberRole.VIEWER: 1,
}


def require_role(minimum_role: MemberRole) -> Depends:
    """FastAPI dependency that enforces a minimum role level.

    API key auth is not subject to RBAC (API keys have their own scope
    system).  JWT auth without a role, or with a role below the minimum,
    receives a 403 response.
    """

    async def _check(request: Request) -> None:
        auth_type = getattr(request.state, "auth_type", None)

        # API keys use scope-based access control, not RBAC.
        if auth_type == "api_key":
            return

        role = getattr(request.state, "role", None)
        if role is None:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_ROLE",
                        "message": "Role not assigned",
                    }
                },
            )

        user_level = _ROLE_HIERARCHY.get(role, 0)
        required_level = _ROLE_HIERARCHY.get(minimum_role, 0)
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": {
                        "code": "INSUFFICIENT_ROLE",
                        "message": f"Requires {minimum_role.value} or higher",
                    }
                },
            )

    return Depends(_check)
