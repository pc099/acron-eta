"""Async trace writer — persists CallTrace, RequestLog, and RoutingDecisionLog.

Runs as a background task (asyncio.create_task) so it never blocks the
gateway critical path. Each write gets its own DB session.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from app.db.engine import async_session_factory
from app.db.models import CallTrace, RequestLog, RoutingDecisionLog

logger = logging.getLogger(__name__)


@dataclass
class TracePayload:
    """All data needed to persist a gateway call trace."""

    org_id: str
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    request_id: Optional[str] = None
    model_requested: Optional[str] = None
    model_used: Optional[str] = None
    provider: Optional[str] = None
    routing_mode: Optional[str] = None
    intervention_mode: Optional[str] = None
    policy_action: Optional[str] = None
    policy_reason: Optional[str] = None
    cache_hit: bool = False
    cache_tier: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: Optional[int] = None
    cost_without_asahi: float = 0.0
    cost_with_asahi: float = 0.0
    savings_usd: float = 0.0
    savings_pct: Optional[float] = None
    semantic_similarity: Optional[float] = None
    model_endpoint_id: Optional[str] = None
    api_key_id: Optional[str] = None
    routing_reason: Optional[str] = None
    routing_factors: Optional[dict] = None
    routing_confidence: Optional[float] = None
    risk_score: Optional[float] = None
    intervention_level: Optional[int] = None
    risk_factors: Optional[dict] = None
    error_message: Optional[str] = None
    trace_metadata: Optional[dict] = None

    # Debug metadata for observability
    cache_metadata: Optional[dict] = None
    routing_metadata: Optional[dict] = None
    intervention_metadata: Optional[dict] = None

    # SDK v2 tool support
    tools_requested: Optional[dict] = None
    tools_called: Optional[dict] = None
    tool_call_count: int = 0
    web_search_enabled: bool = False
    mcp_servers_used: Optional[dict] = None
    computer_use_enabled: bool = False
    chain_id: Optional[str] = None


def _to_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    """Convert a string to UUID, returning None if invalid or empty."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


async def write_trace(payload: TracePayload) -> None:
    """Persist CallTrace, RequestLog, and RoutingDecisionLog in a single transaction.

    Designed to run as a fire-and-forget background task.
    """
    try:
        async with async_session_factory() as session:
            org_uuid = uuid.UUID(payload.org_id)
            agent_uuid = _to_uuid(payload.agent_id)
            session_uuid = _to_uuid(payload.agent_session_id)
            endpoint_uuid = _to_uuid(payload.model_endpoint_id)
            api_key_uuid = _to_uuid(payload.api_key_id)

            # Merge risk_factors and debug metadata into trace_metadata
            meta = dict(payload.trace_metadata or {})
            if payload.risk_factors:
                meta["risk_factors"] = payload.risk_factors
            if payload.cache_metadata:
                meta["cache_debug"] = payload.cache_metadata
            if payload.routing_metadata:
                meta["routing_debug"] = payload.routing_metadata
            if payload.intervention_metadata:
                meta["intervention_debug"] = payload.intervention_metadata

            # Convert chain_id to UUID
            chain_uuid = _to_uuid(payload.chain_id)

            # 1. Write CallTrace
            call_trace = CallTrace(
                organisation_id=org_uuid,
                agent_id=agent_uuid,
                agent_session_id=session_uuid,
                request_id=payload.request_id,
                model_requested=payload.model_requested,
                model_used=payload.model_used,
                provider=payload.provider,
                routing_mode=payload.routing_mode,
                intervention_mode=payload.intervention_mode,
                policy_action=payload.policy_action,
                policy_reason=payload.policy_reason,
                cache_hit=payload.cache_hit,
                cache_tier=payload.cache_tier,
                input_tokens=payload.input_tokens,
                output_tokens=payload.output_tokens,
                latency_ms=payload.latency_ms,
                risk_score=payload.risk_score,
                intervention_level=payload.intervention_level,
                trace_metadata=meta,
                # SDK v2 tool support
                tools_requested=payload.tools_requested,
                tools_called=payload.tools_called,
                tool_call_count=payload.tool_call_count,
                web_search_enabled=payload.web_search_enabled,
                mcp_servers_used=payload.mcp_servers_used,
                computer_use_enabled=payload.computer_use_enabled,
                chain_id=chain_uuid,
            )
            session.add(call_trace)
            await session.flush()

            # 2. Write RequestLog
            status_code = 200 if not payload.error_message else 500
            cost_original = payload.cost_without_asahi or 0.0
            cost_with = payload.cost_with_asahi or 0.0
            savings = payload.savings_usd or (cost_original - cost_with)
            savings_pct = payload.savings_pct
            if savings_pct is None and cost_original > 0:
                savings_pct = round(savings / cost_original * 100, 2)

            # Map cache_tier string to CacheType enum
            cache_type = None
            if payload.cache_tier:
                from app.db.models import CacheType
                tier_map = {
                    "exact": CacheType.EXACT,
                    "semantic": CacheType.SEMANTIC,
                    "intermediate": CacheType.INTERMEDIATE,
                }
                cache_type = tier_map.get(payload.cache_tier, CacheType.MISS)

            request_log = RequestLog(
                organisation_id=org_uuid,
                api_key_id=api_key_uuid,
                agent_id=agent_uuid,
                agent_session_id=session_uuid,
                model_endpoint_id=endpoint_uuid,
                request_id=payload.request_id,
                model_requested=payload.model_requested,
                model_used=payload.model_used or "unknown",
                provider=payload.provider,
                routing_mode=payload.routing_mode,
                intervention_mode=payload.intervention_mode,
                input_tokens=payload.input_tokens,
                output_tokens=payload.output_tokens,
                cost_without_asahi=cost_original,
                cost_with_asahi=cost_with,
                savings_usd=savings,
                savings_pct=savings_pct,
                cache_hit=payload.cache_hit,
                cache_tier=cache_type,
                semantic_similarity=payload.semantic_similarity,
                latency_ms=payload.latency_ms,
                status_code=status_code,
                error_message=payload.error_message,
            )
            session.add(request_log)

            # Link request_log to call_trace
            call_trace.request_log_id = request_log.id

            # 3. Write RoutingDecisionLog
            routing_decision = RoutingDecisionLog(
                organisation_id=org_uuid,
                agent_id=agent_uuid,
                call_trace_id=call_trace.id,
                routing_mode=payload.routing_mode,
                intervention_mode=payload.intervention_mode,
                selected_model=payload.model_used,
                selected_provider=payload.provider,
                confidence=payload.routing_confidence,
                decision_summary=payload.routing_reason,
                factors=payload.routing_factors or {},
            )
            session.add(routing_decision)

            await session.commit()
            logger.debug(
                "Trace written: call_trace=%s request_log=%s routing_decision=%s",
                call_trace.id,
                request_log.id,
                routing_decision.id,
            )

            # Publish to SSE live trace subscribers
            try:
                from app.api.traces import publish_trace_event

                publish_trace_event(payload.org_id, {
                    "id": str(call_trace.id),
                    "agent_id": str(agent_uuid) if agent_uuid else None,
                    "agent_session_id": str(session_uuid) if session_uuid else None,
                    "request_id": payload.request_id,
                    "model_requested": payload.model_requested,
                    "model_used": payload.model_used,
                    "provider": payload.provider,
                    "routing_mode": payload.routing_mode,
                    "intervention_mode": payload.intervention_mode,
                    "policy_action": payload.policy_action,
                    "cache_hit": payload.cache_hit,
                    "cache_tier": payload.cache_tier,
                    "input_tokens": payload.input_tokens,
                    "output_tokens": payload.output_tokens,
                    "latency_ms": payload.latency_ms,
                    "risk_score": float(payload.risk_score) if payload.risk_score is not None else None,
                    "intervention_level": payload.intervention_level,
                    "savings_usd": payload.savings_usd,
                }
                )
            except Exception:
                logger.debug("SSE publish failed (no subscribers or import error)")
    except Exception as exc:
        logger.exception("Failed to write trace for org %s", payload.org_id)

        # Send critical alert for trace write failure (data loss event)
        try:
            import asyncio
            import traceback
            from app.core.alerts import alert_trace_write_failure

            asyncio.create_task(
                alert_trace_write_failure(
                    org_id=payload.org_id,
                    trace_id=payload.request_id,
                    error=str(exc),
                    stack_trace=traceback.format_exc(),
                )
            )
        except Exception:
            logger.error("Failed to send trace write failure alert")
