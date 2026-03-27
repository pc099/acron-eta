"""Intervention resource for the ASAHIO Python SDK."""

from __future__ import annotations

from typing import Optional

from asahio.resources import AsyncResource, PaginatedList, SyncResource, _strip_none
from asahio.types.interventions import FleetOverview, InterventionLog, InterventionStats


class Interventions(SyncResource):
    """Sync intervention resource."""

    def list_logs(
        self,
        *,
        agent_id: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedList[InterventionLog]:
        """List intervention logs."""
        params = _strip_none({
            "agent_id": agent_id,
            "action_type": action_type,
            "limit": limit,
            "offset": offset,
        })
        response = self._client.get("/interventions", params=params)
        data = response.json()
        return PaginatedList(
            data=[InterventionLog.from_dict(log) for log in data.get("data", [])],
            total=data.get("pagination", {}).get("total", 0),
            limit=limit,
            offset=offset,
        )

    def get_stats(self, *, agent_id: Optional[str] = None) -> InterventionStats:
        """Get intervention statistics."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = self._client.get("/interventions/stats", params=params if params else None)
        return InterventionStats.from_dict(response.json())

    def fleet_overview(self) -> FleetOverview:
        """Get fleet-wide intervention overview."""
        response = self._client.get("/interventions/fleet-overview")
        return FleetOverview.from_dict(response.json())


class AsyncInterventions(AsyncResource):
    """Async intervention resource."""

    async def list_logs(
        self,
        *,
        agent_id: Optional[str] = None,
        action_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedList[InterventionLog]:
        """List intervention logs."""
        params = _strip_none({
            "agent_id": agent_id,
            "action_type": action_type,
            "limit": limit,
            "offset": offset,
        })
        response = await self._client.get("/interventions", params=params)
        data = response.json()
        return PaginatedList(
            data=[InterventionLog.from_dict(log) for log in data.get("data", [])],
            total=data.get("pagination", {}).get("total", 0),
            limit=limit,
            offset=offset,
        )

    async def get_stats(self, *, agent_id: Optional[str] = None) -> InterventionStats:
        """Get intervention statistics."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id

        response = await self._client.get("/interventions/stats", params=params if params else None)
        return InterventionStats.from_dict(response.json())

    async def fleet_overview(self) -> FleetOverview:
        """Get fleet-wide intervention overview."""
        response = await self._client.get("/interventions/fleet-overview")
        return FleetOverview.from_dict(response.json())
