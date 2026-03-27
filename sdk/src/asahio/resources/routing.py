"""Routing resource for the ASAHIO Python SDK."""

from __future__ import annotations

from typing import Any, Optional

from asahio.resources import AsyncResource, SyncResource
from asahio.types.routing import DryRunResult, RoutingConstraint, RoutingDecision


class Routing(SyncResource):
    """Sync routing resource."""

    def dry_run(
        self,
        *,
        rule_type: str,
        rule_config: dict,
        prompt: str = "Test prompt for dry-run",
        session_step: Optional[int] = None,
        utc_hour: Optional[int] = None,
    ) -> DryRunResult:
        """Dry run a routing rule without executing."""
        body: dict[str, Any] = {
            "rule_type": rule_type,
            "rule_config": rule_config,
            "prompt": prompt,
        }
        if session_step is not None:
            body["session_step"] = session_step
        if utc_hour is not None:
            body["utc_hour"] = utc_hour

        response = self._client.post("/routing/rules/dry-run", json=body)
        data = response.json()
        return DryRunResult.from_dict(data.get("data", data))

    def get_decision(self, call_id: str) -> RoutingDecision:
        """Get routing decision for a specific call."""
        response = self._client.get(f"/routing/decisions/{call_id}")
        return RoutingDecision.from_dict(response.json())

    def list_constraints(self, *, agent_id: Optional[str] = None) -> list[RoutingConstraint]:
        """List routing constraints."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = self._client.get("/routing/constraints", params=params if params else None)
        data = response.json()
        return [RoutingConstraint.from_dict(c) for c in data.get("data", [])]

    def create_constraint(
        self,
        *,
        agent_id: str,
        constraint_type: str,
        value: Any,
        priority: int = 0,
    ) -> RoutingConstraint:
        """Create a new routing constraint."""
        body = {
            "agent_id": agent_id,
            "rule_type": constraint_type,
            "rule_config": value if isinstance(value, dict) else {"value": value},
            "priority": priority,
        }
        response = self._client.post("/routing/constraints", json=body)
        data = response.json()
        return RoutingConstraint.from_dict(data.get("data", data))

    def delete_constraint(self, constraint_id: str) -> dict:
        """Delete a routing constraint."""
        response = self._client.delete(f"/routing/constraints/{constraint_id}")
        return response.json()


class AsyncRouting(AsyncResource):
    """Async routing resource."""

    async def dry_run(
        self,
        *,
        rule_type: str,
        rule_config: dict,
        prompt: str = "Test prompt for dry-run",
        session_step: Optional[int] = None,
        utc_hour: Optional[int] = None,
    ) -> DryRunResult:
        """Dry run a routing rule without executing."""
        body: dict[str, Any] = {
            "rule_type": rule_type,
            "rule_config": rule_config,
            "prompt": prompt,
        }
        if session_step is not None:
            body["session_step"] = session_step
        if utc_hour is not None:
            body["utc_hour"] = utc_hour

        response = await self._client.post("/routing/rules/dry-run", json=body)
        data = response.json()
        # Backend wraps result in {"data": {...}}
        return DryRunResult.from_dict(data.get("data", data))

    async def get_decision(self, call_id: str) -> RoutingDecision:
        """Get routing decision for a specific call."""
        response = await self._client.get(f"/routing/decisions/{call_id}")
        return RoutingDecision.from_dict(response.json())

    async def list_constraints(self, *, agent_id: Optional[str] = None) -> list[RoutingConstraint]:
        """List routing constraints."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = await self._client.get("/routing/constraints", params=params if params else None)
        data = response.json()
        return [RoutingConstraint.from_dict(c) for c in data.get("data", [])]

    async def create_constraint(
        self,
        *,
        agent_id: str,
        constraint_type: str,
        value: Any,
        priority: int = 0,
    ) -> RoutingConstraint:
        """Create a new routing constraint."""
        body = {
            "agent_id": agent_id,
            "rule_type": constraint_type,
            "rule_config": value if isinstance(value, dict) else {"value": value},
            "priority": priority,
        }
        response = await self._client.post("/routing/constraints", json=body)
        data = response.json()
        return RoutingConstraint.from_dict(data.get("data", data))

    async def delete_constraint(self, constraint_id: str) -> dict:
        """Delete a routing constraint."""
        response = await self._client.delete(f"/routing/constraints/{constraint_id}")
        return response.json()
