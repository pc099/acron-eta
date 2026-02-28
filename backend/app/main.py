"""FastAPI application factory for ASAHI SaaS backend."""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.api import admin, analytics, auth, gateway, governance, keys, orgs
from app.config import get_settings
from app.db import engine as _db_engine_mod
from app.db.models import Base
from app.middleware.auth import AuthMiddleware
from app.middleware.cors_preflight import CORSPreflightMiddleware
from app.middleware.metering import MeteringMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)

# Tables that reference users; drop in FK order so create_all can recreate with UUID.
_USER_DEPENDENT_TABLES = (
    "invitations",
    "audit_logs",
    "request_logs",
    "api_keys",
    "members",
    "users",
)


def _drop_user_dependent_tables(connection) -> None:
    """Drop tables that reference users so they can be recreated with UUID user_id."""
    for table in _USER_DEPENDENT_TABLES:
        connection.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE'))


def _check_and_fix_users_id_type(connection) -> None:
    """If users.id is not UUID (e.g. integer), drop user-dependent tables so create_all can recreate with UUID."""
    result = connection.execute(
        text(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'users' AND column_name = 'id'
            """
        )
    )
    row = result.fetchone()
    if not row or str(row[0]).lower() == "uuid":
        return
    logger.warning(
        "Detected users.id as %s (expected uuid); dropping user-dependent tables so schema can be recreated.",
        row[0],
    )
    _drop_user_dependent_tables(connection)


async def _ensure_schema() -> None:
    """Run schema fix if needed, then create_all. Retry once after dropping user tables if create_all fails with FK type mismatch."""
    _engine = _db_engine_mod.engine  # Use module attribute (overridable by tests)

    # PostgreSQL-specific schema migration — skip for SQLite (tests)
    if _engine.url.drivername.startswith("postgresql"):
        async with _engine.begin() as conn:
            await conn.run_sync(_check_and_fix_users_id_type)

    try:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except ProgrammingError as e:
        msg = str(e).lower()
        if "user_id" in msg and "incompatible types" in msg:
            logger.warning(
                "create_all failed (users.id type mismatch); dropping user-dependent tables and retrying: %s",
                e,
            )
            async with _engine.begin() as conn:
                await conn.run_sync(_drop_user_dependent_tables)
            async with _engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        else:
            raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: fix schema if needed, create tables + connect Redis. Shutdown: cleanup."""
    settings = get_settings()

    await _ensure_schema()

    # Connect to Redis
    try:
        app.state.redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        await app.state.redis.ping()
        logger.info("Redis connected at %s", settings.redis_url)

        # Set up semantic cache vector index
        try:
            from app.services.cache import RedisCache

            cache = RedisCache(app.state.redis)
            await cache.setup_semantic_index()
        except Exception:
            logger.warning("Semantic cache index setup failed — semantic cache disabled")
    except Exception:
        logger.warning("Redis not available — rate limiting and caching disabled")
        app.state.redis = None

    yield

    # Shutdown
    if app.state.redis:
        await app.state.redis.close()
    await _db_engine_mod.engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title="ASAHI API",
        version="1.0.0",
        description="LLM Inference Optimization Platform — route, cache, save.",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # CORS: last added runs first. Preflight handles OPTIONS with 200; CORSMiddleware adds headers to other responses.
    origins = settings.cors_origins
    allow_credentials = True
    if origins == ["*"]:
        allow_credentials = False  # Browser forbids * with credentials
        logger.warning("CORS_ORIGINS=* disables credentials; use exact origins in production")
    logger.info("CORS allow_origins=%s allow_credentials=%s", origins, allow_credentials)

    app.add_middleware(MeteringMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    # Handle OPTIONS with 200 + CORS headers first (avoids 400 from CORSMiddleware in some setups)
    app.add_middleware(
        CORSPreflightMiddleware,
        allow_origins=origins,
        allow_credentials=allow_credentials,
    )

    # Routers
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(gateway.router, prefix="/v1", tags=["gateway"])
    app.include_router(orgs.router, prefix="/orgs", tags=["organisations"])
    app.include_router(keys.router, prefix="/keys", tags=["api-keys"])
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
    app.include_router(governance.router, prefix="/governance", tags=["governance"])
    app.include_router(admin.router, prefix="/admin", tags=["admin"])

    @app.get("/health")
    async def health():
        redis_ok = False
        if hasattr(app.state, "redis") and app.state.redis:
            try:
                await app.state.redis.ping()
                redis_ok = True
            except Exception:
                pass

        return {
            "status": "ok",
            "version": "1.0.0",
            "redis": "connected" if redis_ok else "unavailable",
            "cors_origins": settings.cors_origins,
            "debug": settings.debug,
        }

    return app


app = create_app()
