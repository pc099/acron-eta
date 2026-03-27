"""Provider management routes — BYOK keys, Ollama configs, and guided chains."""

from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.engine import get_db
from app.db.models import ChainSlot, GuidedChain, MemberRole, OllamaConfig, ProviderKey
from app.middleware.rbac import require_role
from app.schemas.providers import (
    VALID_PROVIDERS,
    VALID_TRIGGERS,
    ChainCreateRequest,
    ChainResponse,
    ChainSlotResponse,
    ChainTestResponse,
    ChainTestSlotResult,
    OllamaConfigResponse,
    OllamaVerifyRequest,
    ProviderKeyCreateRequest,
    ProviderKeyResponse,
)
from app.services.encryption import encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id) if isinstance(org_id, str) else org_id


def _serialize_key(pk: ProviderKey) -> dict:
    return ProviderKeyResponse(
        id=str(pk.id),
        organisation_id=str(pk.organisation_id),
        provider=pk.provider,
        key_hint=pk.key_hint,
        is_active=pk.is_active,
        last_used_at=pk.last_used_at,
        created_at=pk.created_at,
    ).model_dump()


def _serialize_ollama(config: OllamaConfig) -> dict:
    return OllamaConfigResponse(
        id=str(config.id),
        organisation_id=str(config.organisation_id),
        name=config.name,
        base_url=config.base_url,
        is_verified=config.is_verified,
        available_models=config.available_models or [],
        last_verified_at=config.last_verified_at,
        is_active=config.is_active,
        created_at=config.created_at,
    ).model_dump()


def _serialize_chain(chain: GuidedChain, slots: list[ChainSlot] | None = None) -> dict:
    if slots is None:
        slots = list(chain.slots) if chain.slots else []
    slots = sorted(slots, key=lambda s: s.priority)
    return ChainResponse(
        id=str(chain.id),
        organisation_id=str(chain.organisation_id),
        name=chain.name,
        fallback_triggers=chain.fallback_triggers or [],
        is_default=chain.is_default,
        is_active=chain.is_active,
        slots=[
            ChainSlotResponse(
                id=str(s.id),
                chain_id=str(s.chain_id),
                provider=s.provider,
                model=s.model,
                priority=s.priority,
                max_latency_ms=s.max_latency_ms,
                max_cost_per_1k_tokens=float(s.max_cost_per_1k_tokens) if s.max_cost_per_1k_tokens else None,
            )
            for s in slots
        ],
        created_at=chain.created_at,
    ).model_dump()


# ── BYOK Key Management ───────────────────────────────────────────────


@router.post("/keys", status_code=201, dependencies=[require_role(MemberRole.ADMIN)])
async def store_provider_key(
    body: ProviderKeyCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Store an encrypted BYOK API key for a provider."""
    org_id = await _get_org_id(request)

    if body.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider. Must be one of: {', '.join(sorted(VALID_PROVIDERS))}")

    # Upsert: deactivate any existing key for this provider
    result = await db.execute(
        select(ProviderKey).where(
            ProviderKey.organisation_id == org_id,
            ProviderKey.provider == body.provider,
            ProviderKey.is_active == True,  # noqa: E712
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_active = False

    encrypted = encrypt_secret(body.api_key)
    key_hint = f"...{body.api_key[-4:]}" if len(body.api_key) >= 4 else None

    pk = ProviderKey(
        id=uuid.uuid4(),
        organisation_id=org_id,
        provider=body.provider,
        encrypted_key=encrypted,
        key_hint=key_hint,
    )
    db.add(pk)
    await db.flush()
    return _serialize_key(pk)


@router.get("/keys")
async def list_provider_keys(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List stored BYOK keys for the organisation (masked)."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(ProviderKey)
        .where(ProviderKey.organisation_id == org_id, ProviderKey.is_active == True)  # noqa: E712
        .order_by(ProviderKey.created_at.desc())
    )
    keys = result.scalars().all()
    return {"data": [_serialize_key(pk) for pk in keys]}


@router.delete("/keys/{key_id}", status_code=204, response_model=None, dependencies=[require_role(MemberRole.ADMIN)])
async def delete_provider_key(
    key_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a BYOK key."""
    org_id = await _get_org_id(request)
    pk = await db.get(ProviderKey, uuid.UUID(key_id))
    if not pk or pk.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Provider key not found")
    pk.is_active = False
    await db.flush()


# ── Ollama Self-Hosted ─────────────────────────────────────────────────


@router.post("/ollama/verify", status_code=201, dependencies=[require_role(MemberRole.ADMIN)])
async def verify_ollama(
    body: OllamaVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify connectivity to an Ollama instance and save config."""
    org_id = await _get_org_id(request)

    # Verify connectivity
    available_models: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{body.base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            available_models = [m.get("name", "") for m in data.get("models", [])]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ollama connectivity failed: {exc}")

    # Upsert config
    result = await db.execute(
        select(OllamaConfig).where(
            OllamaConfig.organisation_id == org_id,
            OllamaConfig.base_url == body.base_url,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.is_verified = True
        existing.available_models = available_models
        existing.name = body.name or existing.name
        from datetime import datetime, timezone
        existing.last_verified_at = datetime.now(timezone.utc)
        await db.flush()
        return _serialize_ollama(existing)

    from datetime import datetime, timezone
    config = OllamaConfig(
        id=uuid.uuid4(),
        organisation_id=org_id,
        name=body.name,
        base_url=body.base_url,
        is_verified=True,
        available_models=available_models,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(config)
    await db.flush()
    return _serialize_ollama(config)


@router.get("/ollama")
async def list_ollama_configs(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List Ollama configs for the organisation."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(OllamaConfig)
        .where(OllamaConfig.organisation_id == org_id, OllamaConfig.is_active == True)  # noqa: E712
        .order_by(OllamaConfig.created_at.desc())
    )
    configs = result.scalars().all()
    return {"data": [_serialize_ollama(c) for c in configs]}


@router.delete("/ollama/{config_id}", status_code=204, response_model=None, dependencies=[require_role(MemberRole.ADMIN)])
async def delete_ollama_config(
    config_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove an Ollama config."""
    org_id = await _get_org_id(request)
    config = await db.get(OllamaConfig, uuid.UUID(config_id))
    if not config or config.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Ollama config not found")
    config.is_active = False
    await db.flush()


# ── Guided Chains ──────────────────────────────────────────────────────


@router.post("/chains", status_code=201, dependencies=[require_role(MemberRole.ADMIN)])
async def create_chain(
    body: ChainCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a guided chain with 1-3 slots."""
    org_id = await _get_org_id(request)

    # Validate triggers
    invalid = set(body.fallback_triggers) - VALID_TRIGGERS
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid trigger types: {', '.join(invalid)}")

    # Validate slot priorities
    priorities = [s.priority for s in body.slots]
    if 1 not in priorities:
        raise HTTPException(status_code=400, detail="At least one slot with priority 1 is required")
    if len(priorities) != len(set(priorities)):
        raise HTTPException(status_code=400, detail="Slot priorities must be unique")

    chain = GuidedChain(
        id=uuid.uuid4(),
        organisation_id=org_id,
        name=body.name,
        fallback_triggers=body.fallback_triggers,
        is_default=body.is_default,
    )
    db.add(chain)
    await db.flush()

    created_slots: list[ChainSlot] = []
    for slot_req in body.slots:
        slot = ChainSlot(
            id=uuid.uuid4(),
            chain_id=chain.id,
            provider=slot_req.provider,
            model=slot_req.model,
            priority=slot_req.priority,
            max_latency_ms=slot_req.max_latency_ms,
            max_cost_per_1k_tokens=slot_req.max_cost_per_1k_tokens,
        )
        db.add(slot)
        created_slots.append(slot)

    await db.flush()

    # Build response from in-memory objects (avoids lazy-load issues)
    return _serialize_chain(chain, slots=created_slots)


@router.get("/chains")
async def list_chains(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List guided chains for the organisation."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(GuidedChain)
        .options(selectinload(GuidedChain.slots))
        .where(GuidedChain.organisation_id == org_id, GuidedChain.is_active == True)  # noqa: E712
        .order_by(GuidedChain.created_at.desc())
    )
    chains = result.scalars().all()
    return {"data": [_serialize_chain(c) for c in chains]}


@router.get("/chains/{chain_id}")
async def get_chain(
    chain_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single chain with its slots."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(GuidedChain)
        .options(selectinload(GuidedChain.slots))
        .where(GuidedChain.id == uuid.UUID(chain_id))
    )
    chain = result.scalar_one_or_none()
    if not chain or chain.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Chain not found")
    return _serialize_chain(chain)


@router.delete("/chains/{chain_id}", status_code=204, response_model=None, dependencies=[require_role(MemberRole.ADMIN)])
async def delete_chain(
    chain_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a chain (cascade deletes slots)."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(GuidedChain).where(GuidedChain.id == uuid.UUID(chain_id))
    )
    chain = result.scalar_one_or_none()
    if not chain or chain.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Chain not found")
    await db.delete(chain)
    await db.flush()


@router.post("/chains/{chain_id}/test")
async def test_chain(
    chain_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dry-run: check if all slots can resolve keys."""
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(GuidedChain)
        .options(selectinload(GuidedChain.slots))
        .where(GuidedChain.id == uuid.UUID(chain_id))
    )
    chain = result.scalar_one_or_none()
    if not chain or chain.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Chain not found")

    from app.services.key_resolver import DBKeyResolver
    resolver = DBKeyResolver(db)

    slot_results: list[ChainTestSlotResult] = []
    all_ready = True

    for slot in sorted(chain.slots, key=lambda s: s.priority):
        try:
            await resolver.resolve(slot.provider, str(org_id))
            slot_results.append(ChainTestSlotResult(
                position=slot.priority,
                provider=slot.provider,
                model=slot.model,
                key_available=True,
            ))
        except (ValueError, Exception) as exc:
            all_ready = False
            slot_results.append(ChainTestSlotResult(
                position=slot.priority,
                provider=slot.provider,
                model=slot.model,
                key_available=False,
                error=str(exc),
            ))

    return ChainTestResponse(
        chain_id=str(chain.id),
        ready=all_ready,
        slots=slot_results,
    ).model_dump()


# ── Provider Health Dashboard ───────────────────────────────────────────


@router.get("/health")
async def get_provider_health_dashboard(request: Request):
    """Get comprehensive provider health status including circuit breaker state.

    Returns real-time health status for all configured providers including:
    - Provider health status (healthy/degraded/unreachable)
    - Circuit breaker state (CLOSED/HALF_OPEN/OPEN)
    - Failure count
    - Time until recovery (for open circuits)

    This endpoint is used by the provider health dashboard in the frontend.
    """
    from app.services.provider_health import get_all_provider_health
    from app.core.optimizer import _provider_circuits

    # Get provider health from health checker
    provider_health = get_all_provider_health()

    # Build comprehensive health status
    health_status = []

    for provider, health in provider_health.items():
        # Get circuit breaker state if it exists
        circuit = _provider_circuits.get(provider)

        circuit_info = {
            "state": "CLOSED",
            "failure_count": 0,
            "recovery_remaining_seconds": 0,
        }

        if circuit:
            circuit_info = {
                "state": circuit.state.value,
                "failure_count": circuit._failure_count,
                "recovery_remaining_seconds": round(circuit.recovery_remaining(), 1),
            }

        health_status.append({
            "provider": provider,
            "health": health,
            "circuit_breaker": circuit_info,
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        })

    return {
        "providers": health_status,
        "total_providers": len(health_status),
        "healthy_count": sum(1 for p in health_status if p["health"] == "healthy"),
        "degraded_count": sum(1 for p in health_status if p["health"] == "degraded"),
        "unreachable_count": sum(1 for p in health_status if p["health"] == "unreachable"),
    }
