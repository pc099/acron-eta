"""Background task queue with retry using arq (Redis-based).

Provides reliable background job execution with automatic retries for:
- Trace writing (CallTrace, RequestLog, RoutingDecisionLog)
- ABA observation recording
- Cache storage (semantic cache to Pinecone)

Jobs are retried up to 3 times with exponential backoff (1s, 5s, 15s).
If all retries fail, an alert is sent and the job is marked as failed.

Deploy worker:
    arq app.core.task_queue.WorkerSettings

Environment variables:
    REDIS_URL - Redis connection string
"""

import logging
import os
from dataclasses import asdict
from typing import Any, Optional

from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import func

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task Functions
# ---------------------------------------------------------------------------


async def write_trace_task(ctx: dict, payload_dict: dict) -> None:
    """Background task that writes trace to database with retry.

    Args:
        ctx: arq context (contains redis, job_id, etc.)
        payload_dict: TracePayload as dict

    Raises:
        Exception: On failure (arq will retry automatically)
    """
    from app.services.trace_writer import TracePayload, write_trace

    payload = TracePayload(**payload_dict)

    try:
        await write_trace(payload)
        logger.info(
            "Trace written successfully",
            extra={
                "org_id": payload.org_id,
                "request_id": payload.request_id,
                "job_id": ctx.get("job_id"),
            }
        )
    except Exception as exc:
        logger.error(
            "Trace write failed in arq task, will retry",
            extra={
                "org_id": payload.org_id,
                "request_id": payload.request_id,
                "error": str(exc),
                "job_id": ctx.get("job_id"),
                "job_try": ctx.get("job_try", 0),
            },
            exc_info=True
        )
        raise  # arq will retry


async def write_aba_observation_task(ctx: dict, payload_dict: dict) -> None:
    """Background task that writes ABA observation with retry.

    Args:
        ctx: arq context
        payload_dict: ABA observation payload as dict

    Raises:
        Exception: On failure (arq will retry)
    """
    # Import here to avoid circular dependencies
    from app.services.aba_writer import write_aba_observation

    try:
        await write_aba_observation(payload_dict)
        logger.info(
            "ABA observation written",
            extra={
                "org_id": payload_dict.get("org_id"),
                "agent_id": payload_dict.get("agent_id"),
                "job_id": ctx.get("job_id"),
            }
        )
    except Exception as exc:
        logger.error(
            "ABA observation write failed, will retry",
            extra={
                "org_id": payload_dict.get("org_id"),
                "error": str(exc),
                "job_id": ctx.get("job_id"),
                "job_try": ctx.get("job_try", 0),
            },
            exc_info=True
        )
        raise


async def store_cache_task(
    ctx: dict,
    org_id: str,
    prompt: str,
    response: str,
    model_used: str,
) -> None:
    """Background task that stores response in semantic cache with retry.

    Args:
        ctx: arq context
        org_id: Organization ID
        prompt: User prompt (for embedding)
        response: Model response
        model_used: Model that generated the response

    Raises:
        Exception: On failure (arq will retry)
    """
    from app.services.semantic_cache import store_in_cache

    try:
        # Get Redis from app state (available in ctx)
        redis = ctx.get("redis")
        if not redis:
            logger.warning("Redis not available in ctx, skipping cache storage")
            return

        await store_in_cache(redis, org_id, prompt, response, model_used)
        logger.debug(
            "Cache stored successfully",
            extra={
                "org_id": org_id,
                "model_used": model_used,
                "job_id": ctx.get("job_id"),
            }
        )
    except Exception as exc:
        logger.error(
            "Cache storage failed, will retry",
            extra={
                "org_id": org_id,
                "error": str(exc),
                "job_id": ctx.get("job_id"),
                "job_try": ctx.get("job_try", 0),
            },
            exc_info=True
        )
        raise


async def on_job_failure(ctx: dict) -> None:
    """Called when a job fails after all retries exhausted.

    Sends critical alert for permanent failures.

    Args:
        ctx: arq context with job info
    """
    job_id = ctx.get("job_id")
    job_try = ctx.get("job_try", 0)
    job_name = ctx.get("job_name", "unknown")

    logger.critical(
        "Background task failed permanently after all retries",
        extra={
            "job_id": job_id,
            "job_name": job_name,
            "job_try": job_try,
        }
    )

    # Send alert
    try:
        from app.core.alerts import alert_background_task_failure

        await alert_background_task_failure(
            task_name=job_name,
            error=f"Failed after {job_try} retries",
            retry_count=job_try,
            context={"job_id": job_id},
        )
    except Exception as exc:
        logger.error("Failed to send background task failure alert: %s", exc)


# ---------------------------------------------------------------------------
# Worker Settings
# ---------------------------------------------------------------------------


async def startup(ctx: dict) -> None:
    """Called once when worker starts up.

    Sets up shared resources in ctx that all tasks can access.

    Args:
        ctx: arq context dictionary
    """
    logger.info("arq worker starting up")

    # Add Redis to context for tasks that need it
    try:
        import redis.asyncio as aioredis
        from app.config import get_settings

        settings = get_settings()
        ctx["redis"] = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
        await ctx["redis"].ping()
        logger.info("Worker Redis connection established")
    except Exception as exc:
        logger.warning("Worker Redis connection failed: %s", exc)
        ctx["redis"] = None


async def shutdown(ctx: dict) -> None:
    """Called once when worker shuts down.

    Cleans up shared resources.

    Args:
        ctx: arq context dictionary
    """
    logger.info("arq worker shutting down")

    # Close Redis if it was created
    if ctx.get("redis"):
        await ctx["redis"].close()


class WorkerSettings:
    """arq worker configuration.

    Defines:
    - Task functions to register
    - Redis connection settings
    - Retry policy (max tries, delays)
    - Startup/shutdown hooks
    """

    functions = [
        write_trace_task,
        write_aba_observation_task,
        store_cache_task,
    ]

    on_startup = startup
    on_shutdown = shutdown
    on_job_failure = on_job_failure

    # Redis settings
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379")
    )

    # Retry policy
    max_tries = 3
    job_timeout = 60  # 60 seconds timeout per job
    keep_result = 3600  # Keep job results for 1 hour

    # Retry delays (exponential backoff)
    # Try 0: immediate
    # Try 1: wait 1 second
    # Try 2: wait 5 seconds
    # Try 3: wait 15 seconds
    retry_jobs = True
    job_retry_delays = [1, 5, 15]  # seconds between retries


# ---------------------------------------------------------------------------
# Helper Functions (for enqueueing jobs)
# ---------------------------------------------------------------------------


_pool: Optional[Any] = None


async def get_arq_pool() -> Any:
    """Get or create the global arq connection pool.

    Returns:
        arq Redis pool for enqueueing jobs

    Example:
        pool = await get_arq_pool()
        await pool.enqueue_job("write_trace_task", payload_dict)
    """
    global _pool
    if _pool is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        _pool = await create_pool(RedisSettings.from_dsn(redis_url))
    return _pool


async def enqueue_trace_write(payload_dict: dict) -> Optional[str]:
    """Enqueue trace write job.

    Args:
        payload_dict: TracePayload as dict

    Returns:
        Job ID if enqueued successfully, None if pool unavailable

    Example:
        from dataclasses import asdict
        job_id = await enqueue_trace_write(asdict(trace_payload))
    """
    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job("write_trace_task", payload_dict)
        return job.job_id if job else None
    except Exception as exc:
        logger.error("Failed to enqueue trace write job: %s", exc)
        return None


async def enqueue_aba_observation(payload_dict: dict) -> Optional[str]:
    """Enqueue ABA observation write job.

    Args:
        payload_dict: ABA observation payload as dict

    Returns:
        Job ID if enqueued successfully, None if pool unavailable
    """
    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job("write_aba_observation_task", payload_dict)
        return job.job_id if job else None
    except Exception as exc:
        logger.error("Failed to enqueue ABA observation job: %s", exc)
        return None


async def enqueue_cache_storage(
    org_id: str,
    prompt: str,
    response: str,
    model_used: str,
) -> Optional[str]:
    """Enqueue cache storage job.

    Args:
        org_id: Organization ID
        prompt: User prompt
        response: Model response
        model_used: Model identifier

    Returns:
        Job ID if enqueued successfully, None if pool unavailable
    """
    try:
        pool = await get_arq_pool()
        job = await pool.enqueue_job(
            "store_cache_task",
            org_id,
            prompt,
            response,
            model_used,
        )
        return job.job_id if job else None
    except Exception as exc:
        logger.error("Failed to enqueue cache storage job: %s", exc)
        return None
