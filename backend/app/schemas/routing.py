"""Pydantic schemas for routing constraint CRUD."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ConstraintCreate(BaseModel):
    """Request body for creating a routing constraint."""

    agent_id: Optional[uuid.UUID] = Field(
        default=None, description="Agent to scope this rule to. Null = org-wide."
    )
    rule_type: str = Field(
        ..., description="Rule type: step_based, time_based, fallback_chain, cost_ceiling_per_1k, model_allowlist, provider_restriction"
    )
    rule_config: dict = Field(..., description="Rule configuration payload")
    priority: int = Field(default=0, description="Override auto-priority (higher wins)")


class ConstraintUpdate(BaseModel):
    """Request body for updating a routing constraint."""

    rule_config: Optional[dict] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


class ConstraintResponse(BaseModel):
    """Response shape for a routing constraint."""

    id: uuid.UUID
    organisation_id: uuid.UUID
    agent_id: Optional[uuid.UUID] = None
    rule_type: str
    rule_config: dict
    priority: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
