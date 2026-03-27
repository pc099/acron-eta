"""Chain (fallback chain) resource for the ASAHIO Python SDK."""

from __future__ import annotations

from typing import Any, Optional

from asahio.resources import AsyncResource, SyncResource
from asahio.types.providers import Chain, ChainTestResult


class Chains(SyncResource):
    """Sync chain resource."""

    def list(self) -> list[Chain]:
        """List all chains for the organization."""
        response = self._client.get("/providers/chains")
        data = response.json()
        return [Chain.from_dict(c) for c in data.get("data", [])]

    def create(
        self,
        *,
        name: str,
        slots: list[dict[str, Any]],
        description: Optional[str] = None,
    ) -> Chain:
        """Create a new fallback chain."""
        body: dict[str, Any] = {
            "name": name,
            "slots": slots,
        }
        if description is not None:
            body["description"] = description

        response = self._client.post("/providers/chains", json=body)
        return Chain.from_dict(response.json())

    def get(self, chain_id: str) -> Chain:
        """Get a specific chain by ID."""
        response = self._client.get(f"/providers/chains/{chain_id}")
        return Chain.from_dict(response.json())

    def delete(self, chain_id: str) -> dict:
        """Delete a chain."""
        response = self._client.delete(f"/providers/chains/{chain_id}")
        if response.status_code == 204:
            return {"status": "deleted"}
        return response.json()

    def test(self, chain_id: str, *, prompt: str = "Hello") -> ChainTestResult:
        """Test a chain with a sample prompt."""
        body = {"prompt": prompt}
        response = self._client.post(f"/providers/chains/{chain_id}/test", json=body)
        return ChainTestResult.from_dict(response.json())


class AsyncChains(AsyncResource):
    """Async chain resource."""

    async def list(self) -> list[Chain]:
        """List all chains for the organization."""
        response = await self._client.get("/providers/chains")
        data = response.json()
        return [Chain.from_dict(c) for c in data.get("data", [])]

    async def create(
        self,
        *,
        name: str,
        slots: list[dict[str, Any]],
        description: Optional[str] = None,
    ) -> Chain:
        """Create a new fallback chain."""
        body: dict[str, Any] = {
            "name": name,
            "slots": slots,
        }
        if description is not None:
            body["description"] = description

        response = await self._client.post("/providers/chains", json=body)
        return Chain.from_dict(response.json())

    async def get(self, chain_id: str) -> Chain:
        """Get a specific chain by ID."""
        response = await self._client.get(f"/providers/chains/{chain_id}")
        return Chain.from_dict(response.json())

    async def delete(self, chain_id: str) -> dict:
        """Delete a chain."""
        response = await self._client.delete(f"/providers/chains/{chain_id}")
        if response.status_code == 204:
            return {"status": "deleted"}
        return response.json()

    async def test(self, chain_id: str, *, prompt: str = "Hello") -> ChainTestResult:
        """Test a chain with a sample prompt."""
        body = {"prompt": prompt}
        response = await self._client.post(f"/providers/chains/{chain_id}/test", json=body)
        return ChainTestResult.from_dict(response.json())
