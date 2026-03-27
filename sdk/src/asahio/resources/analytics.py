"""Analytics resource for the ASAHIO Python SDK."""

from __future__ import annotations

from typing import Optional

from asahio.resources import AsyncResource, SyncResource
from asahio.types.analytics import CachePerformance, ModelBreakdown, Overview, SavingsEntry


class Analytics(SyncResource):
    """Sync analytics resource."""

    def overview(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Overview:
        """Get analytics overview."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = self._client.get("/analytics/overview", params=params if params else None)
        return Overview.from_dict(response.json())

    def model_breakdown(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[ModelBreakdown]:
        """Get model usage breakdown."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = self._client.get("/analytics/models", params=params if params else None)
        data = response.json()
        return [ModelBreakdown.from_dict(m) for m in data.get("data", [])]

    def cache_performance(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> CachePerformance:
        """Get cache performance metrics."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = self._client.get("/analytics/cache", params=params if params else None)
        return CachePerformance.from_dict(response.json())

    def savings(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[SavingsEntry]:
        """Get cost savings breakdown."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = self._client.get("/analytics/savings", params=params if params else None)
        data = response.json()
        return [SavingsEntry.from_dict(s) for s in data.get("data", [])]


class AsyncAnalytics(AsyncResource):
    """Async analytics resource."""

    async def overview(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Overview:
        """Get analytics overview."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = await self._client.get("/analytics/overview", params=params if params else None)
        return Overview.from_dict(response.json())

    async def model_breakdown(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[ModelBreakdown]:
        """Get model usage breakdown."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = await self._client.get("/analytics/models", params=params if params else None)
        data = response.json()
        return [ModelBreakdown.from_dict(m) for m in data.get("data", [])]

    async def cache_performance(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> CachePerformance:
        """Get cache performance metrics."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = await self._client.get("/analytics/cache", params=params if params else None)
        return CachePerformance.from_dict(response.json())

    async def savings(
        self,
        *,
        agent_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[SavingsEntry]:
        """Get cost savings breakdown."""
        params = {}
        if agent_id is not None:
            params["agent_id"] = agent_id
        if start_date is not None:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        response = await self._client.get("/analytics/savings", params=params if params else None)
        data = response.json()
        return [SavingsEntry.from_dict(s) for s in data.get("data", [])]
