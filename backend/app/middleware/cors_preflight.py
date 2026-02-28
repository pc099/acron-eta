"""Handle CORS preflight (OPTIONS) with 200 so browsers allow the actual request.

Starlette CORSMiddleware can return 400 in some cases; this ensures OPTIONS
always gets 200 with correct CORS headers when the origin is allowed.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CORSPreflightMiddleware(BaseHTTPMiddleware):
    """Respond to OPTIONS with 200 and CORS headers. Runs first (add last)."""

    def __init__(self, app, allow_origins: list[str], allow_credentials: bool = False):
        super().__init__(app)
        self._allow_origins = set(allow_origins) if allow_origins else set()
        self._allow_all = "*" in self._allow_origins or not self._allow_origins
        self._allow_credentials = allow_credentials and not self._allow_all

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method != "OPTIONS":
            return await call_next(request)

        origin = (request.headers.get("origin") or "").strip()
        if self._allow_all:
            allow_origin = "*"
        elif origin and origin in self._allow_origins:
            allow_origin = origin
        elif self._allow_origins:
            allow_origin = next(iter(self._allow_origins))
        else:
            allow_origin = "*"

        headers = {
            "Access-Control-Allow-Origin": allow_origin,
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Max-Age": "600",
        }
        if self._allow_credentials and allow_origin != "*":
            headers["Access-Control-Allow-Credentials"] = "true"
        return Response(status_code=200, headers=headers)
