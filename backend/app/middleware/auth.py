"""Authentication middleware — handles both JWT (dashboard) and API key (SDK) auth.

Rules:
1. Public paths skip auth entirely: /health, /auth/*, /docs, /openapi.json
2. Dashboard paths require JWT from Clerk
3. Gateway paths (/v1/*) require API key OR JWT
4. On success: attach org_id, user_id, org, plan, auth_type to request.state
5. API key auth: SHA-256 hash incoming Bearer token, lookup in api_keys table
6. JWT auth: Verify Clerk JWT signature via JWKS, resolve user + org
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone

import jwt
from jwt import PyJWKClient
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.config import get_settings
from app.db.engine import async_session_factory
from app.db.models import ApiKey, Member, Organisation, User

logger = logging.getLogger(__name__)

# Clerk JWKS client — cached, fetches public keys to verify JWT signatures.
_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    """Lazily initialise the JWKS client from Clerk's issuer URL."""
    global _jwks_client
    if _jwks_client is not None:
        return _jwks_client
    settings = get_settings()
    jwks_url = settings.clerk_jwks_url
    if not jwks_url:
        # Derive from Clerk publishable key or fall back to None
        pk = settings.clerk_publishable_key
        if pk:
            # pk_test_<base64> or pk_live_<base64> — extract the frontend API domain
            import base64
            try:
                # The publishable key encodes the Clerk frontend API domain
                encoded = pk.split("_", 2)[-1]
                # Add padding
                padded = encoded + "=" * (-len(encoded) % 4)
                domain = base64.b64decode(padded).decode("utf-8").rstrip("$")
                jwks_url = f"https://{domain}/.well-known/jwks.json"
            except Exception:
                logger.warning("Could not derive JWKS URL from publishable key")
                return None
        else:
            return None
    _jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
    logger.info("JWKS client initialised: %s", jwks_url)
    return _jwks_client

PUBLIC_PATH_PREFIXES = (
    "/health",
    "/auth/",
    "/docs",
    "/openapi.json",
    "/redoc",
)

# Scope → allowed path prefixes. "*" scope grants full access.
SCOPE_PATH_MAP: dict[str, list[str]] = {
    "inference": ["/v1/"],
    "analytics": ["/analytics/"],
    "keys": ["/keys"],
    "governance": ["/governance/"],
    "admin": ["/admin/"],
}


def _check_scopes(scopes: list, path: str) -> bool:
    """Return True if any scope in the list grants access to the path."""
    if "*" in scopes:
        return True
    for scope in scopes:
        prefixes = SCOPE_PATH_MAP.get(scope, [])
        if any(path.startswith(p) for p in prefixes):
            return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Authenticate requests via API key or Clerk JWT."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip auth for public paths
        path = request.url.path
        if any(path.startswith(p) for p in PUBLIC_PATH_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer asahi_"):
            return await self._auth_api_key(auth_header, request, call_next)
        elif auth_header.startswith("Bearer ey"):
            return await self._auth_jwt(auth_header, request, call_next)
        elif not auth_header:
            return JSONResponse(
                {"error": {"code": "auth_required", "message": "Authentication required"}},
                status_code=401,
            )
        else:
            return JSONResponse(
                {"error": {"code": "invalid_auth", "message": "Invalid authorization header"}},
                status_code=401,
            )

    async def _auth_api_key(
        self, auth_header: str, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Authenticate via ASAHI API key (for SDK/gateway requests)."""
        raw_key = auth_header.removeprefix("Bearer ")
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        async with async_session_factory() as session:
            result = await session.execute(
                select(ApiKey).where(
                    ApiKey.key_hash == key_hash,
                    ApiKey.is_active.is_(True),
                )
            )
            api_key = result.scalar_one_or_none()

            if not api_key:
                return JSONResponse(
                    {"error": {"code": "invalid_api_key", "message": "Invalid or revoked API key"}},
                    status_code=401,
                )

            org = await session.get(Organisation, api_key.organisation_id)
            if not org:
                return JSONResponse(
                    {"error": {"code": "org_not_found", "message": "Organisation not found"}},
                    status_code=401,
                )

            # Enforce scopes
            key_scopes = api_key.scopes or ["*"]
            if not _check_scopes(key_scopes, request.url.path):
                return JSONResponse(
                    {"error": {"code": "insufficient_scope", "message": f"API key lacks required scope for {request.url.path}"}},
                    status_code=403,
                )

            request.state.org_id = str(api_key.organisation_id)
            request.state.org = org
            request.state.api_key_id = str(api_key.id)
            request.state.user_id = None
            request.state.plan = org.plan
            request.state.auth_type = "api_key"

        # Fire-and-forget: update last_used_at
        asyncio.create_task(
            _update_key_last_used(uuid.UUID(request.state.api_key_id))
        )

        return await call_next(request)

    async def _auth_jwt(
        self, auth_header: str, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Authenticate via Clerk JWT (for dashboard requests)."""
        token = auth_header.removeprefix("Bearer ")

        try:
            jwks = _get_jwks_client()
            if jwks:
                signing_key = jwks.get_signing_key_from_jwt(token)
                payload = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["RS256"],
                    options={"verify_aud": False},
                )
            else:
                # Fallback: no JWKS configured — decode without verification (dev only)
                logger.warning("JWKS not configured — skipping JWT signature verification")
                payload = jwt.decode(
                    token,
                    options={"verify_signature": False},
                    algorithms=["RS256"],
                )
        except jwt.PyJWTError as e:
            logger.warning("JWT verification failed: %s", e)
            return JSONResponse(
                {"error": {"code": "invalid_token", "message": "Invalid or expired token"}},
                status_code=401,
            )

        clerk_user_id = payload.get("sub")
        org_id = payload.get("org_id")
        # Dashboard can send current org via header so backend uses correct org
        org_slug = request.headers.get("X-Org-Slug", "").strip() or None

        if not clerk_user_id:
            return JSONResponse(
                {"error": {"code": "invalid_token", "message": "Token missing subject"}},
                status_code=401,
            )

        async with async_session_factory() as session:
            # Look up user by Clerk ID
            result = await session.execute(
                select(User).where(User.clerk_user_id == clerk_user_id)
            )
            user = result.scalar_one_or_none()

            if not user:
                return JSONResponse(
                    {"error": {"code": "user_not_found", "message": "User not found"}},
                    status_code=401,
                )

            # Prefer X-Org-Slug from dashboard, then org_id from JWT
            if org_slug:
                org_result = await session.execute(
                    select(Organisation).where(Organisation.slug == org_slug)
                )
                org = org_result.scalar_one_or_none()
                if not org:
                    return JSONResponse(
                        {"error": {"code": "org_not_found", "message": "Organisation not found"}},
                        status_code=404,
                    )
                member_result = await session.execute(
                    select(Member).where(
                        Member.organisation_id == org.id,
                        Member.user_id == user.id,
                    )
                )
                member = member_result.scalar_one_or_none()
                if not member:
                    return JSONResponse(
                        {"error": {"code": "not_member", "message": "Not a member of this organisation"}},
                        status_code=403,
                    )
                request.state.org_id = str(org.id)
                request.state.org = org
                request.state.plan = org.plan
                request.state.role = member.role
            # If org_id is in the JWT, verify membership
            elif org_id:
                org = await session.get(Organisation, uuid.UUID(org_id))
                if not org:
                    return JSONResponse(
                        {"error": {"code": "org_not_found", "message": "Organisation not found"}},
                        status_code=404,
                    )

                member_result = await session.execute(
                    select(Member).where(
                        Member.organisation_id == uuid.UUID(org_id),
                        Member.user_id == user.id,
                    )
                )
                member = member_result.scalar_one_or_none()
                if not member:
                    return JSONResponse(
                        {"error": {"code": "not_member", "message": "Not a member of this organisation"}},
                        status_code=403,
                    )

                request.state.org_id = org_id
                request.state.org = org
                request.state.plan = org.plan
                request.state.role = member.role
            else:
                # No org in JWT — get first org the user belongs to
                member_result = await session.execute(
                    select(Member).where(Member.user_id == user.id).limit(1)
                )
                member = member_result.scalar_one_or_none()
                if member:
                    org = await session.get(Organisation, member.organisation_id)
                    request.state.org_id = str(member.organisation_id)
                    request.state.org = org
                    request.state.plan = org.plan if org else None
                    request.state.role = member.role
                else:
                    request.state.org_id = None
                    request.state.org = None
                    request.state.plan = None
                    request.state.role = None

            request.state.user_id = str(user.id)
            request.state.auth_type = "jwt"

        return await call_next(request)


async def _update_key_last_used(api_key_id: uuid.UUID) -> None:
    """Fire-and-forget update of API key last_used_at timestamp."""
    try:
        async with async_session_factory() as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.id == api_key_id)
                .values(last_used_at=datetime.now(timezone.utc))
            )
            await session.commit()
    except Exception:
        logger.exception("Failed to update api key last_used_at")
