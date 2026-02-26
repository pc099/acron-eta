"""Gateway route — OpenAI-compatible proxy wrapping the existing InferenceOptimizer.

POST /v1/chat/completions — Drop-in replacement for OpenAI API.
Includes Redis cache integration, budget checks, and org limit enforcement.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.optimizer import GatewayResult, run_inference
from app.services.metering import is_budget_exceeded, is_rate_limited

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool = False
    routing_mode: str = "AUTOPILOT"
    quality_preference: str = "high"
    latency_preference: str = "normal"


@router.post("/chat/completions")
async def chat_completions(body: ChatCompletionRequest, request: Request):
    """OpenAI-compatible chat completions endpoint with ASAHI optimization.

    Flow:
    1. Validate auth (org_id from middleware)
    2. Check org monthly request limit (Redis)
    3. Check org monthly budget (Redis)
    4. Redis cache check (exact → semantic)
    5. On cache miss: call InferenceOptimizer.infer() from src/
    6. Store in Redis cache (fire-and-forget)
    7. Return OpenAI-compatible response + asahi{} metadata
    8. Metering middleware logs usage AFTER response
    """
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")

    org = getattr(request.state, "org", None)
    redis = getattr(request.app.state, "redis", None)

    # Check monthly request limit
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

        # Check monthly budget
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

    # Extract last user message as the prompt
    user_messages = [m for m in body.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in messages")

    prompt = user_messages[-1].content

    # Run inference (includes Redis cache check + optimizer fallback)
    result: GatewayResult = await run_inference(
        prompt=prompt,
        routing_mode=body.routing_mode,
        quality_preference=body.quality_preference,
        latency_preference=body.latency_preference,
        model_override=body.model,
        org_id=org_id,
        use_mock=True,
        redis=redis,
    )

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

    # Store result in request.state for metering middleware
    request.state.inference_result = result

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:24]}",
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
        "asahi": {
            "cache_hit": result.cache_hit,
            "cache_tier": result.cache_tier,
            "model_requested": body.model,
            "model_used": result.model_used,
            "cost_without_asahi": result.cost_without_asahi,
            "cost_with_asahi": result.cost_with_asahi,
            "savings_usd": result.savings_usd,
            "savings_pct": result.savings_pct,
            "routing_reason": result.routing_reason,
        },
    }
