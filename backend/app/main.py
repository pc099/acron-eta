"""FastAPI application factory for ASAHI SaaS backend."""

import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, analytics, auth, gateway, keys, orgs
from app.config import get_settings
from app.db.engine import engine
from app.db.models import Base
from app.middleware.auth import AuthMiddleware
from app.middleware.metering import MeteringMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables + connect Redis. Shutdown: cleanup."""
    settings = get_settings()

    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

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
    await engine.dispose()


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

    # CORS — allow frontend origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters — outermost runs first)
    app.add_middleware(MeteringMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    # Routers
    app.include_router(auth.router, prefix="/auth", tags=["auth"])
    app.include_router(gateway.router, prefix="/v1", tags=["gateway"])
    app.include_router(orgs.router, prefix="/orgs", tags=["organisations"])
    app.include_router(keys.router, prefix="/keys", tags=["api-keys"])
    app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
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
        }

    return app


app = create_app()
