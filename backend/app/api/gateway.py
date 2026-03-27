"""OpenAI-compatible gateway route for the ASAHIO backend."""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.optimizer import GatewayResult, normalize_routing_mode, run_inference
from app.db.engine import get_db
from app.db.models import Agent, AgentSession, GuidedChain, InterventionMode, ModelEndpoint
from app.services.metering import is_budget_exceeded, is_rate_limited
from app.services.aba_writer import ABAObservationPayload, write_aba_observation
from app.services.trace_writer import TracePayload, write_trace

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    routing_mode: str | None = None
    intervention_mode: str | None = None
    quality_preference: str = "high"
    latency_preference: str = "normal"
    agent_id: str | None = None
    session_id: str | None = None
    model_endpoint_id: str | None = None
    chain_id: str | None = None
    bypass_cache: bool = False  # Skip cache lookup/storage for write-back loops

    # SDK v2 agentic parameters
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    enable_web_search: bool = False
    web_search_config: dict | None = None
    mcp_servers: list[dict] | None = None
    enable_computer_use: bool = False
    computer_use_config: dict | None = None


async def _resolve_agent(db: AsyncSession, org_id: str, agent_id: str | None) -> Agent | None:
    if not agent_id:
        return None
    agent = await db.get(Agent, uuid.UUID(agent_id))
    if not agent or str(agent.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _resolve_model_endpoint(
    db: AsyncSession,
    org_id: str,
    model_endpoint_id: str | None,
) -> ModelEndpoint | None:
    if not model_endpoint_id:
        return None
    endpoint = await db.get(ModelEndpoint, uuid.UUID(model_endpoint_id))
    if not endpoint or str(endpoint.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Model endpoint not found")
    return endpoint


async def _resolve_session(
    db: AsyncSession,
    org_id: str,
    agent: Agent | None,
    external_session_id: str | None,
) -> AgentSession | None:
    if not external_session_id:
        return None
    if not agent:
        raise HTTPException(status_code=400, detail="session_id requires agent_id")

    result = await db.execute(
        select(AgentSession).where(
            AgentSession.organisation_id == uuid.UUID(org_id),
            AgentSession.agent_id == agent.id,
            AgentSession.external_session_id == external_session_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        session = AgentSession(
            organisation_id=uuid.UUID(org_id),
            agent_id=agent.id,
            external_session_id=external_session_id,
        )
        db.add(session)
        await db.flush()
    else:
        session.last_seen_at = datetime.now(timezone.utc)
        await db.flush()
    return session


def _build_metadata(result: GatewayResult, external_session_id: str | None) -> dict:
    metadata = {
        "cache_hit": result.cache_hit,
        "cache_tier": result.cache_tier,
        "cache_debug": result.cache_metadata,
        "model_requested": result.model_requested,
        "model_used": result.model_used,
        "provider": result.provider,
        "routing_mode": result.routing_mode,
        "intervention_mode": result.intervention_mode,
        "agent_id": result.agent_id,
        "agent_session_id": result.agent_session_id,
        "session_id": external_session_id,
        "model_endpoint_id": result.model_endpoint_id,
        "cost_without_asahio": result.cost_without_asahi,
        "cost_with_asahio": result.cost_with_asahi,
        "cost_without_asahi": result.cost_without_asahi,
        "cost_with_asahi": result.cost_with_asahi,
        "savings_usd": result.savings_usd,
        "savings_pct": result.savings_pct,
        "routing_reason": result.routing_reason,
        "routing_factors": result.routing_factors,
        "routing_confidence": result.routing_confidence,
        "routing_debug": result.routing_metadata,
        "policy_action": result.policy_action,
        "policy_reason": result.policy_reason,
        "risk_score": result.risk_score,
        "risk_factors": result.risk_factors,
        "intervention_level": result.intervention_level,
        "intervention_debug": result.intervention_metadata,
        "request_id": result.request_id,
    }
    return metadata


@router.post("/chat/completions")
async def chat_completions(
    body: ChatCompletionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")

    org = getattr(request.state, "org", None)
    redis = getattr(request.app.state, "redis", None)

    if redis and org:
        if await is_rate_limited(redis, org_id, org.monthly_request_limit):
            return JSONResponse(
                {
                    "error": {
                        "message": "Monthly request limit exceeded. Upgrade your plan for more requests.",
                        "type": "rate_limit_error",
                        "code": "monthly_limit_exceeded",
                    }
                },
                status_code=429,
            )

        budget = float(org.monthly_budget_usd) if org.monthly_budget_usd else 0
        if budget > 0 and await is_budget_exceeded(redis, org_id, budget):
            return JSONResponse(
                {
                    "error": {
                        "message": "Monthly budget exceeded.",
                        "type": "budget_exceeded",
                        "code": "budget_exceeded",
                    }
                },
                status_code=402,
            )

    user_messages = [message for message in body.messages if message.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in messages")

    prompt = user_messages[-1].content
    agent = await _resolve_agent(db, org_id, body.agent_id)
    effective_model_endpoint_id = body.model_endpoint_id or (
        str(agent.model_endpoint_id) if agent and agent.model_endpoint_id else None
    )
    model_endpoint = await _resolve_model_endpoint(db, org_id, effective_model_endpoint_id)
    session = await _resolve_session(db, org_id, agent, body.session_id)

    # Resolve guided chain if chain_id is provided
    chain_config = None
    if body.chain_id:
        from sqlalchemy.orm import selectinload
        chain_result = await db.execute(
            select(GuidedChain)
            .options(selectinload(GuidedChain.slots))
            .where(GuidedChain.id == uuid.UUID(body.chain_id))
        )
        chain = chain_result.scalar_one_or_none()
        if not chain or str(chain.organisation_id) != org_id:
            raise HTTPException(status_code=404, detail="Chain not found")
        chain_config = {
            "chain_id": str(chain.id),
            "name": chain.name,
            "fallback_triggers": chain.fallback_triggers or [],
            "slots": [
                {
                    "position": s.priority,
                    "model_id": s.model,
                    "provider": s.provider,
                    "max_latency_ms": s.max_latency_ms,
                    "max_cost_per_1k_tokens": float(s.max_cost_per_1k_tokens) if s.max_cost_per_1k_tokens else None,
                }
                for s in sorted(chain.slots, key=lambda s: s.priority)
            ],
        }

    effective_routing_mode = normalize_routing_mode(
        body.routing_mode or (agent.routing_mode.value if agent else None)
    )
    effective_intervention_mode = (
        body.intervention_mode
        or (agent.intervention_mode.value if agent else InterventionMode.OBSERVE.value)
    ).upper()
    model_override = body.model or (model_endpoint.model_id if model_endpoint else None)

    # Look up fingerprint for risk scoring (fast Redis-cached in production)
    fingerprint_hallucination_rate = None
    agent_type_hint = None
    threshold_overrides = None
    session_step = None
    if agent:
        try:
            from app.db.models import AgentFingerprint
            fp_result = await db.execute(
                select(AgentFingerprint).where(AgentFingerprint.agent_id == agent.id)
            )
            fp = fp_result.scalar_one_or_none()
            if fp:
                fingerprint_hallucination_rate = float(fp.hallucination_rate)
        except Exception:
            pass  # Not critical — risk scorer has fallbacks
        threshold_overrides = agent.risk_threshold_overrides
    if session:
        try:
            from app.db.models import CallTrace as CT
            step_result = await db.execute(
                select(func.count(CT.id)).where(
                    CT.agent_session_id == session.id,
                    CT.organisation_id == uuid.UUID(org_id),
                )
            )
            session_step = (step_result.scalar() or 0) + 1
        except Exception:
            session_step = None

    result: GatewayResult = await run_inference(
        prompt=prompt,
        routing_mode=effective_routing_mode,
        intervention_mode=effective_intervention_mode,
        quality_preference=body.quality_preference,
        latency_preference=body.latency_preference,
        model_override=model_override,
        org_id=org_id,
        agent_id=str(agent.id) if agent else None,
        agent_session_id=str(session.id) if session else None,
        model_endpoint_id=str(model_endpoint.id) if model_endpoint else None,
        provider_hint=model_endpoint.provider if model_endpoint else None,
        use_mock=get_settings().debug,
        redis=redis,
        session_step=session_step,
        fingerprint_hallucination_rate=fingerprint_hallucination_rate,
        agent_type=agent_type_hint,
        threshold_overrides=threshold_overrides,
        chain_config=chain_config,
        bypass_cache=body.bypass_cache,
    )
    result.model_requested = body.model or (model_endpoint.model_id if model_endpoint else body.model)

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    if not result.request_id:
        result.request_id = completion_id

    # Fire background trace persistence — never blocks the response
    api_key_id = getattr(getattr(request.state, "api_key", None), "id", None)
    # Extract tool information for trace
    tools_requested = None
    if body.tools:
        tools_requested = {"tools": body.tools, "tool_choice": body.tool_choice}

    # Extract MCP server names if provided
    mcp_servers_used = None
    if body.mcp_servers:
        mcp_servers_used = {"servers": [s.get("name") for s in body.mcp_servers if isinstance(s, dict)]}

    trace_payload = TracePayload(
        org_id=org_id,
        agent_id=str(agent.id) if agent else None,
        agent_session_id=str(session.id) if session else None,
        request_id=result.request_id,
        model_requested=result.model_requested,
        model_used=result.model_used,
        provider=result.provider,
        routing_mode=result.routing_mode,
        intervention_mode=result.intervention_mode,
        policy_action=result.policy_action,
        policy_reason=result.policy_reason,
        cache_hit=result.cache_hit,
        cache_tier=result.cache_tier,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        cost_without_asahi=result.cost_without_asahi,
        cost_with_asahi=result.cost_with_asahi,
        savings_usd=result.savings_usd,
        savings_pct=result.savings_pct,
        model_endpoint_id=str(model_endpoint.id) if model_endpoint else None,
        api_key_id=str(api_key_id) if api_key_id else None,
        routing_reason=result.routing_reason,
        routing_factors=result.routing_factors,
        routing_confidence=result.routing_confidence,
        risk_score=result.risk_score,
        intervention_level=result.intervention_level,
        risk_factors=result.risk_factors,
        error_message=result.error_message,
        # Debug metadata for observability
        cache_metadata=result.cache_metadata,
        routing_metadata=result.routing_metadata,
        intervention_metadata=result.intervention_metadata,
        # SDK v2 tool support
        tools_requested=tools_requested,
        tools_called=result.tools_called if hasattr(result, "tools_called") else None,
        tool_call_count=result.tool_call_count if hasattr(result, "tool_call_count") else 0,
        web_search_enabled=body.enable_web_search,
        mcp_servers_used=mcp_servers_used,
        computer_use_enabled=body.enable_computer_use,
        chain_id=body.chain_id,
        # ABA / Model C observation fields
        agent_type=result.agent_type,
        complexity_score=result.complexity_score or result.risk_score,
        output_type=result.output_type,
        hallucination_detected=result.hallucination_detected,
    )

    # Enqueue trace write with arq (retryable background task)
    try:
        from dataclasses import asdict
        from app.core.task_queue import enqueue_trace_write

        asyncio.create_task(enqueue_trace_write(asdict(trace_payload)))
    except Exception as exc:
        logger.warning("Failed to enqueue trace write, falling back to direct write: %s", exc)
        asyncio.create_task(write_trace(trace_payload))

    # Fire ABA observation — never blocks the response
    if agent:
        aba_payload = ABAObservationPayload(
            org_id=org_id,
            agent_id=str(agent.id),
            prompt=prompt,
            response=result.response or "",
            model_used=result.model_used or "unknown",
            latency_ms=result.latency_ms,
            cache_hit=result.cache_hit or False,
            input_tokens=result.input_tokens or 0,
            output_tokens=result.output_tokens or 0,
        )

        # Enqueue ABA observation with arq (retryable background task)
        try:
            from dataclasses import asdict
            from app.core.task_queue import enqueue_aba_observation

            asyncio.create_task(enqueue_aba_observation(asdict(aba_payload)))
        except Exception as exc:
            logger.warning("Failed to enqueue ABA observation, falling back to direct write: %s", exc)
            asyncio.create_task(write_aba_observation(aba_payload))

    if result.error_message:
        return JSONResponse(
            {
                "error": {
                    "message": result.error_message,
                    "type": "inference_error",
                    "code": "inference_failed",
                }
            },
            status_code=500,
        )

    request.state.inference_result = result
    metadata = _build_metadata(result, body.session_id)

    if body.stream:
        metadata["streaming"] = "simulated"
        return StreamingResponse(
            _stream_response(completion_id, result, metadata),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return {
        "id": completion_id,
        "object": "chat.completion",
        "model": result.model_used,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.response},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "total_tokens": result.input_tokens + result.output_tokens,
        },
        "asahio": metadata,
        "asahi": metadata,
    }


async def _stream_response(completion_id: str, result: GatewayResult, metadata: dict):
    """Yield SSE chunks from a pre-computed response.

    NOTE: This is *simulated* streaming. The full LLM response is generated
    first, then chunked into word-level SSE events. Real token-by-token
    streaming from the provider is not yet implemented. Operators should be
    aware this does NOT reduce time-to-first-token.
    """

    def _chunk(content: Optional[str], finish_reason: Optional[str]) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "model": result.model_used,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": content} if content else {},
                    "finish_reason": finish_reason,
                }
            ],
        }
        return f"data: {json.dumps(payload)}\n\n"

    words = result.response.split(" ")
    for index, word in enumerate(words):
        token = word if index == 0 else f" {word}"
        yield _chunk(token, None)
        await asyncio.sleep(0.02)

    yield _chunk(None, "stop")
    event_payload = {
        **metadata,
        "usage": {
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
            "total_tokens": result.input_tokens + result.output_tokens,
        },
    }
    yield f"event: asahio\ndata: {json.dumps(event_payload)}\n\n"
    yield f"event: asahi\ndata: {json.dumps(event_payload)}\n\n"
    yield "data: [DONE]\n\n"




