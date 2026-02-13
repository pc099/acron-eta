"""
Multi-tenancy manager for tenant isolation.

Ensures data, cache namespaces, and metrics are fully isolated
between organisations.  Supports starter, professional, and
enterprise plan tiers with configurable limits.
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.config import get_settings

logger = logging.getLogger(__name__)


# ── Data Models ────────────────────────────────────────


class TenancyConfig(BaseModel):
    """Configuration for MultiTenancyManager.

    Attributes:
        cache_namespace_prefix: Prefix for tenant cache namespaces.
        plan_limits: Per-plan resource limits.
    """

    cache_namespace_prefix: str = Field(
        default_factory=lambda: get_settings().governance.tenancy_cache_namespace_prefix
    )
    plan_limits: Dict[str, Dict[str, int]] = Field(
        default_factory=lambda: {
            "starter": {
                "max_requests_per_day": 1_000,
                "max_models": 3,
                "max_users": 5,
            },
            "professional": {
                "max_requests_per_day": 10_000,
                "max_models": 10,
                "max_users": 50,
            },
            "enterprise": {
                "max_requests_per_day": 100_000,
                "max_models": 100,
                "max_users": 1_000,
            },
        }
    )


class Tenant(BaseModel):
    """Tenant (organisation) record.

    Attributes:
        org_id: Unique organisation identifier.
        name: Display name.
        plan: Subscription tier.
        created_at: Creation timestamp.
        settings: Arbitrary key-value settings.
    """

    org_id: str
    name: str
    plan: Literal["starter", "professional", "enterprise"] = "starter"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    settings: Dict[str, Any] = Field(default_factory=dict)


class MultiTenancyManager:
    """Tenant lifecycle and isolation manager.

    Args:
        config: Tenancy configuration.
    """

    def __init__(self, config: Optional[TenancyConfig] = None) -> None:
        self._config = config or TenancyConfig()
        self._lock = threading.Lock()
        self._tenants: Dict[str, Tenant] = {}
        self._activity: Dict[str, List[datetime]] = defaultdict(list)
        logger.info("MultiTenancyManager initialised", extra={})

    # ------------------------------------------------------------------
    # Tenant CRUD
    # ------------------------------------------------------------------

    def create_tenant(self, tenant: Tenant) -> None:
        """Register a new tenant.

        Args:
            tenant: Tenant to create.

        Raises:
            ValueError: If the org_id already exists.
        """
        with self._lock:
            if tenant.org_id in self._tenants:
                raise ValueError(
                    f"Tenant '{tenant.org_id}' already exists"
                )
            self._tenants[tenant.org_id] = tenant
        logger.info(
            "Tenant created",
            extra={"org_id": tenant.org_id, "plan": tenant.plan},
        )

    def get_tenant(self, org_id: str) -> Optional[Tenant]:
        """Retrieve a tenant by org_id.

        Args:
            org_id: Organisation identifier.

        Returns:
            The tenant, or None if not found.
        """
        return self._tenants.get(org_id)

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    def validate_access(self, org_id: str, resource_org_id: str) -> bool:
        """Check if an org may access a resource owned by another org.

        Cross-tenant access is always denied.

        Args:
            org_id: Requesting organisation.
            resource_org_id: Organisation that owns the resource.

        Returns:
            True only if ``org_id == resource_org_id``.
        """
        return org_id == resource_org_id

    # ------------------------------------------------------------------
    # Namespace isolation
    # ------------------------------------------------------------------

    def get_tenant_cache_namespace(self, org_id: str) -> str:
        """Return the cache namespace for a tenant.

        Args:
            org_id: Organisation identifier.

        Returns:
            Namespace string in the format ``{prefix}:{org_id}``.
        """
        return f"{self._config.cache_namespace_prefix}:{org_id}"

    # ------------------------------------------------------------------
    # Metrics / activity
    # ------------------------------------------------------------------

    def record_tenant_activity(self, org_id: str) -> None:
        """Record an activity event for a tenant.

        Args:
            org_id: Organisation identifier.
        """
        with self._lock:
            self._activity[org_id].append(datetime.utcnow())

    def get_tenant_metrics(self, org_id: str) -> Dict[str, Any]:
        """Return usage metrics for a tenant.

        Args:
            org_id: Organisation identifier.

        Returns:
            Dict with plan, limits, and activity counts.
        """
        tenant = self._tenants.get(org_id)
        if not tenant:
            return {"error": "tenant_not_found"}

        plan = tenant.plan
        limits = self._config.plan_limits.get(plan, {})

        with self._lock:
            activity_count = len(self._activity.get(org_id, []))

        return {
            "org_id": org_id,
            "plan": plan,
            "limits": limits,
            "total_requests": activity_count,
            "created_at": tenant.created_at.isoformat(),
        }
