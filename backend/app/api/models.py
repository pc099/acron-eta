"""Model registry routes for BYOM configuration."""

from __future__ import annotations

import re
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import MemberRole, ModelEndpoint, ModelEndpointType
from app.middleware.rbac import require_role
from app.services.encryption import encrypt_secret

router = APIRouter()


def _encrypt_if_present(value: Optional[str]) -> Optional[str]:
    """Encrypt a secret reference if provided."""
    if value is None:
        return None
    try:
        return encrypt_secret(value)
    except Exception:
        return value


class ModelEndpointRequest(BaseModel):
    name: str
    endpoint_type: str = ModelEndpointType.PLATFORM.value
    provider: str = "asahio"
    model_id: str
    endpoint_url: Optional[str] = None
    secret_reference: Optional[str] = None
    default_headers: dict = Field(default_factory=dict)
    capability_flags: dict = Field(default_factory=dict)
    fallback_model_id: Optional[str] = None
    validate_health: bool = False


class ModelEndpointUpdateRequest(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_id: Optional[str] = None
    endpoint_url: Optional[str] = None
    secret_reference: Optional[str] = None
    default_headers: Optional[dict] = None
    capability_flags: Optional[dict] = None
    fallback_model_id: Optional[str] = None
    is_active: Optional[bool] = None


async def _get_org_id(request: Request) -> uuid.UUID:
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return uuid.UUID(org_id)


def _to_endpoint_type(value: str) -> ModelEndpointType:
    try:
        return ModelEndpointType(value.lower())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid endpoint type") from exc


async def _health_check(url: str, headers: dict) -> tuple[str, Optional[str]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, headers=headers)
            if response.status_code < 500:
                return "healthy", None
            return "degraded", f"HTTP {response.status_code}"
    except Exception as exc:
        return "unreachable", str(exc)


def _serialize_endpoint(endpoint: ModelEndpoint) -> dict:
    return {
        "id": str(endpoint.id),
        "name": endpoint.name,
        "endpoint_type": endpoint.endpoint_type.value,
        "provider": endpoint.provider,
        "model_id": endpoint.model_id,
        "endpoint_url": endpoint.endpoint_url,
        "secret_reference": endpoint.secret_reference,
        "default_headers": endpoint.default_headers or {},
        "capability_flags": endpoint.capability_flags or {},
        "fallback_model_id": endpoint.fallback_model_id,
        "health_status": endpoint.health_status,
        "last_health_error": endpoint.last_health_error,
        "is_active": endpoint.is_active,
        "created_at": endpoint.created_at.isoformat(),
        "updated_at": endpoint.updated_at.isoformat() if endpoint.updated_at else None,
    }


@router.get("")
async def list_model_endpoints(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    org_id = await _get_org_id(request)
    result = await db.execute(
        select(ModelEndpoint)
        .where(ModelEndpoint.organisation_id == org_id)
        .order_by(ModelEndpoint.created_at.desc())
    )
    endpoints = result.scalars().all()
    return {"data": [_serialize_endpoint(endpoint) for endpoint in endpoints]}


@router.post("/register", status_code=201, dependencies=[require_role(MemberRole.ADMIN)])
async def register_model_endpoint(
    body: ModelEndpointRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = await _get_org_id(request)

    # Validate endpoint URL format when provided
    if body.endpoint_url:
        url_pattern = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
        if not url_pattern.match(body.endpoint_url):
            raise HTTPException(status_code=400, detail="Invalid endpoint URL format")

    endpoint = ModelEndpoint(
        organisation_id=org_id,
        name=body.name,
        endpoint_type=_to_endpoint_type(body.endpoint_type),
        provider=body.provider,
        model_id=body.model_id,
        endpoint_url=body.endpoint_url,
        secret_reference=_encrypt_if_present(body.secret_reference),
        default_headers=body.default_headers,
        capability_flags=body.capability_flags,
        fallback_model_id=body.fallback_model_id,
    )

    if body.validate_health and body.endpoint_url:
        health_status, last_error = await _health_check(body.endpoint_url, body.default_headers)
        endpoint.health_status = health_status
        endpoint.last_health_error = last_error
        if health_status == "unreachable":
            raise HTTPException(status_code=400, detail=f"Endpoint validation failed: {last_error}")

    db.add(endpoint)
    await db.flush()
    return _serialize_endpoint(endpoint)


@router.patch("/{endpoint_id}", dependencies=[require_role(MemberRole.ADMIN)])
async def update_model_endpoint(
    endpoint_id: str,
    body: ModelEndpointUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = await _get_org_id(request)
    endpoint = await db.get(ModelEndpoint, uuid.UUID(endpoint_id))
    if not endpoint or endpoint.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Model endpoint not found")

    for field in (
        "name",
        "provider",
        "model_id",
        "endpoint_url",
        "secret_reference",
        "default_headers",
        "capability_flags",
        "fallback_model_id",
        "is_active",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(endpoint, field, value)

    await db.flush()
    return _serialize_endpoint(endpoint)


@router.delete("/{endpoint_id}", status_code=204, response_model=None, dependencies=[require_role(MemberRole.ADMIN)])
async def delete_model_endpoint(
    endpoint_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> None:
    org_id = await _get_org_id(request)
    endpoint = await db.get(ModelEndpoint, uuid.UUID(endpoint_id))
    if not endpoint or endpoint.organisation_id != org_id:
        raise HTTPException(status_code=404, detail="Model endpoint not found")
    await db.delete(endpoint)
