"""API Key routes — CRUD lifecycle.

GET    /keys           — List org's API keys (never return hash or raw key)
POST   /keys           — Create key — return raw_key ONCE, never again
PATCH  /keys/{id}      — Update name/scopes/allowed_models
DELETE /keys/{id}      — Revoke (set is_active=False)
POST   /keys/{id}/rotate — Revoke + create new key, return new raw_key
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import ApiKey, KeyEnvironment
from app.services.audit import write_audit

router = APIRouter()


# ── Schemas ───────────────────────────────────


class KeyCreateRequest(BaseModel):
    name: str
    environment: str = "live"
    scopes: list[str] = ["*"]
    allowed_models: Optional[list[str]] = None


class KeyCreateResponse(BaseModel):
    id: str
    name: str
    raw_key: str
    prefix: str
    last_four: str
    environment: str
    scopes: list[str]
    created_at: datetime


class KeyListItem(BaseModel):
    id: str
    name: str
    environment: str
    prefix: str
    last_four: str
    scopes: list
    allowed_models: Optional[list]
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime


class KeyUpdateRequest(BaseModel):
    name: Optional[str] = None
    scopes: Optional[list[str]] = None
    allowed_models: Optional[list[str]] = None


# ── Helpers ───────────────────────────────────


def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


# ── Routes ────────────────────────────────────


@router.get("", response_model=list[KeyListItem])
async def list_keys(request: Request, db: AsyncSession = Depends(get_db)):
    """List all API keys for the organisation. Never returns hash or raw key."""
    org_id = _get_org_id(request)

    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.organisation_id == org_id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()

    return [
        KeyListItem(
            id=str(k.id),
            name=k.name,
            environment=k.environment.value,
            prefix=k.prefix,
            last_four=k.last_four,
            scopes=k.scopes or [],
            allowed_models=k.allowed_models,
            is_active=k.is_active,
            last_used_at=k.last_used_at,
            created_at=k.created_at,
        )
        for k in keys
    ]


@router.post("", response_model=KeyCreateResponse, status_code=201)
async def create_key(body: KeyCreateRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new API key. Returns the raw key ONCE — it cannot be retrieved again."""
    org_id = _get_org_id(request)
    user_id = getattr(request.state, "user_id", None)

    env = body.environment if body.environment in ("live", "test") else "live"
    raw_key, prefix, key_hash, last_four = ApiKey.generate(environment=env)

    api_key = ApiKey(
        id=uuid.uuid4(),
        organisation_id=org_id,
        created_by_user_id=uuid.UUID(user_id) if user_id else None,
        name=body.name,
        environment=KeyEnvironment(env),
        prefix=prefix,
        key_hash=key_hash,
        last_four=last_four,
        scopes=body.scopes,
        allowed_models=body.allowed_models,
    )
    db.add(api_key)
    await db.flush()

    await write_audit(
        db, org_id=org_id,
        user_id=uuid.UUID(user_id) if user_id else None,
        action="key.created", resource_type="api_key",
        resource_id=str(api_key.id),
        ip_address=request.client.host if request.client else None,
    )

    return KeyCreateResponse(
        id=str(api_key.id),
        name=api_key.name,
        raw_key=raw_key,
        prefix=prefix,
        last_four=last_four,
        environment=env,
        scopes=body.scopes,
        created_at=api_key.created_at,
    )


@router.patch("/{key_id}")
async def update_key(
    key_id: str, body: KeyUpdateRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Update key name, scopes, or allowed models."""
    org_id = _get_org_id(request)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == uuid.UUID(key_id),
            ApiKey.organisation_id == org_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    if body.name is not None:
        api_key.name = body.name
    if body.scopes is not None:
        api_key.scopes = body.scopes
    if body.allowed_models is not None:
        api_key.allowed_models = body.allowed_models

    await db.flush()

    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "scopes": api_key.scopes,
        "allowed_models": api_key.allowed_models,
    }


@router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Revoke an API key (soft delete — sets is_active=False)."""
    org_id = _get_org_id(request)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == uuid.UUID(key_id),
            ApiKey.organisation_id == org_id,
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.is_active = False

    user_id = getattr(request.state, "user_id", None)
    await write_audit(
        db, org_id=org_id,
        user_id=uuid.UUID(user_id) if user_id else None,
        action="key.revoked", resource_type="api_key",
        resource_id=key_id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()


@router.post("/{key_id}/rotate", response_model=KeyCreateResponse)
async def rotate_key(key_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Revoke the old key and create a new one with the same settings."""
    org_id = _get_org_id(request)
    user_id = getattr(request.state, "user_id", None)

    # Revoke old key
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == uuid.UUID(key_id),
            ApiKey.organisation_id == org_id,
        )
    )
    old_key = result.scalar_one_or_none()
    if not old_key:
        raise HTTPException(status_code=404, detail="API key not found")

    old_key.is_active = False

    # Create new key with same settings
    env = old_key.environment.value
    raw_key, prefix, key_hash, last_four = ApiKey.generate(environment=env)

    new_key = ApiKey(
        id=uuid.uuid4(),
        organisation_id=org_id,
        created_by_user_id=uuid.UUID(user_id) if user_id else None,
        name=old_key.name,
        environment=old_key.environment,
        prefix=prefix,
        key_hash=key_hash,
        last_four=last_four,
        scopes=old_key.scopes,
        allowed_models=old_key.allowed_models,
    )
    db.add(new_key)
    await db.flush()

    await write_audit(
        db, org_id=org_id,
        user_id=uuid.UUID(user_id) if user_id else None,
        action="key.rotated", resource_type="api_key",
        resource_id=str(new_key.id),
        ip_address=request.client.host if request.client else None,
        metadata={"old_key_id": key_id},
    )

    return KeyCreateResponse(
        id=str(new_key.id),
        name=new_key.name,
        raw_key=raw_key,
        prefix=prefix,
        last_four=last_four,
        environment=env,
        scopes=new_key.scopes or [],
        created_at=new_key.created_at,
    )
