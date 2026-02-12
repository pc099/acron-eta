"""
Role-Based Access Control and policy enforcement engine.

Manages organisations, users, roles, and per-org policies that
control which models can be used, budget limits, and request caps.
"""

import logging
import threading
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from src.exceptions import BudgetExceededError, PermissionDeniedError

logger = logging.getLogger(__name__)

# ── Data Models ────────────────────────────────────────


class Role(BaseModel):
    """RBAC role with a set of permissions.

    Attributes:
        name: Role identifier.
        permissions: List of permission strings.
        description: Human-readable description.
    """

    name: str
    permissions: List[str]
    description: str = ""


class User(BaseModel):
    """User within an organisation.

    Attributes:
        user_id: Unique user identifier.
        email: User email address.
        org_id: Organisation the user belongs to.
        role: Role name assigned to this user.
        created_at: Account creation timestamp.
        last_active: Last activity timestamp.
        api_key_prefix: Prefix of the user's API key.
    """

    user_id: str
    email: str
    org_id: str
    role: str = "developer"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active: Optional[datetime] = None
    api_key_prefix: Optional[str] = None


class Organization(BaseModel):
    """Organisation (tenant).

    Attributes:
        org_id: Unique organisation identifier.
        name: Display name.
        plan: Subscription tier.
        created_at: Creation timestamp.
        settings: Arbitrary key-value settings.
        compliance_frameworks: Active compliance frameworks.
        data_residency: Required data region.
    """

    org_id: str
    name: str
    plan: Literal["starter", "professional", "enterprise"] = "starter"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    settings: Dict[str, Any] = Field(default_factory=dict)
    compliance_frameworks: List[str] = Field(default_factory=list)
    data_residency: Optional[str] = None


class OrganizationPolicy(BaseModel):
    """Per-organisation governance policy.

    Attributes:
        org_id: Organisation this policy applies to.
        allowed_models: Whitelist; empty means all allowed.
        blocked_models: Blacklist; takes precedence over allowed.
        max_cost_per_day: Daily budget cap (USD).
        max_cost_per_request: Per-request cost cap (USD).
        max_requests_per_day: Daily request count cap.
        default_quality_threshold: Default quality constraint.
        default_latency_budget_ms: Default latency constraint.
        require_audit_log: Whether to force audit logging.
        data_residency: Required data region.
    """

    org_id: str
    allowed_models: List[str] = Field(default_factory=list)
    blocked_models: List[str] = Field(default_factory=list)
    max_cost_per_day: Optional[float] = Field(default=None, ge=0)
    max_cost_per_request: Optional[float] = Field(default=None, ge=0)
    max_requests_per_day: Optional[int] = Field(default=None, ge=0)
    default_quality_threshold: float = Field(default=3.5, ge=0.0, le=5.0)
    default_latency_budget_ms: int = Field(default=300, ge=50)
    require_audit_log: bool = False
    data_residency: Optional[str] = None


class GovernanceConfig(BaseModel):
    """Configuration for GovernanceEngine.

    Attributes:
        budget_tracking_window_hours: Rolling window for budget tracking.
        default_max_requests_per_day: Fallback request cap.
    """

    budget_tracking_window_hours: int = Field(default=24, ge=1)
    default_max_requests_per_day: int = Field(default=10_000, ge=1)


# ── Default roles ──────────────────────────────────────

DEFAULT_ROLES: Dict[str, Role] = {
    "admin": Role(
        name="admin",
        permissions=[
            "infer",
            "view_metrics",
            "view_cost",
            "manage_models",
            "manage_users",
            "manage_policy",
            "view_audit_log",
            "manage_billing",
        ],
        description="Full administrative access",
    ),
    "developer": Role(
        name="developer",
        permissions=["infer", "view_metrics", "view_cost"],
        description="Can run inference and view metrics/cost",
    ),
    "viewer": Role(
        name="viewer",
        permissions=["view_metrics"],
        description="Read-only metrics access",
    ),
    "billing": Role(
        name="billing",
        permissions=[
            "view_metrics",
            "view_cost",
            "view_audit_log",
            "manage_billing",
        ],
        description="Billing and financial management",
    ),
}


class GovernanceEngine:
    """RBAC + policy enforcement engine.

    Args:
        config: Governance configuration.
    """

    def __init__(self, config: Optional[GovernanceConfig] = None) -> None:
        self._config = config or GovernanceConfig()
        self._lock = threading.Lock()
        self._roles: Dict[str, Role] = dict(DEFAULT_ROLES)
        self._users: Dict[str, User] = {}  # user_id -> User
        self._policies: Dict[str, OrganizationPolicy] = {}  # org_id -> policy
        self._orgs: Dict[str, Organization] = {}  # org_id -> org

        # Budget tracking: org_id -> list of (timestamp, cost)
        self._spend_log: Dict[str, List[Tuple[datetime, float]]] = defaultdict(
            list
        )
        # Request count: org_id -> list of timestamps
        self._request_log: Dict[str, List[datetime]] = defaultdict(list)
        logger.info("GovernanceEngine initialised", extra={})

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    def check_permission(
        self, user_id: str, org_id: str, action: str
    ) -> bool:
        """Check whether a user has a specific permission.

        Args:
            user_id: The user to check.
            org_id: The organisation context.
            action: Permission string (e.g. ``infer``).

        Returns:
            True if the user has the permission.
        """
        user = self._users.get(user_id)
        if not user or user.org_id != org_id:
            return False
        role = self._roles.get(user.role)
        if not role:
            return False
        return action in role.permissions

    def get_user_role(self, user_id: str, org_id: str) -> Role:
        """Get the role for a user within an organisation.

        Args:
            user_id: User ID.
            org_id: Organisation ID.

        Returns:
            The user's role.

        Raises:
            PermissionDeniedError: If user is not found in the org.
        """
        user = self._users.get(user_id)
        if not user or user.org_id != org_id:
            raise PermissionDeniedError(
                f"User '{user_id}' not found in org '{org_id}'"
            )
        role = self._roles.get(user.role)
        if not role:
            raise PermissionDeniedError(
                f"Role '{user.role}' not found"
            )
        return role

    def assign_role(
        self, user_id: str, org_id: str, role_name: str
    ) -> None:
        """Assign a role to a user.

        Args:
            user_id: User to update.
            org_id: Organisation context.
            role_name: Role name to assign.

        Raises:
            PermissionDeniedError: If user or role is invalid.
        """
        if role_name not in self._roles:
            raise PermissionDeniedError(f"Role '{role_name}' does not exist")
        user = self._users.get(user_id)
        if not user or user.org_id != org_id:
            raise PermissionDeniedError(
                f"User '{user_id}' not found in org '{org_id}'"
            )
        with self._lock:
            user.role = role_name
        logger.info(
            "Role assigned",
            extra={
                "user_id": user_id,
                "org_id": org_id,
                "role": role_name,
            },
        )

    def register_user(self, user: User) -> None:
        """Register a new user.

        Args:
            user: User to register.
        """
        with self._lock:
            self._users[user.user_id] = user
        logger.info(
            "User registered",
            extra={"user_id": user.user_id, "org_id": user.org_id},
        )

    def list_org_users(self, org_id: str) -> List[Dict[str, Any]]:
        """List all users for an organisation.

        Args:
            org_id: Organisation ID.

        Returns:
            List of user summaries.
        """
        with self._lock:
            return [
                {
                    "user_id": u.user_id,
                    "email": u.email,
                    "role": u.role,
                    "created_at": u.created_at.isoformat(),
                }
                for u in self._users.values()
                if u.org_id == org_id
            ]

    # ------------------------------------------------------------------
    # Policy management
    # ------------------------------------------------------------------

    def create_policy(self, policy: OrganizationPolicy) -> None:
        """Create or replace a policy for an organisation.

        Args:
            policy: The policy to store.
        """
        with self._lock:
            self._policies[policy.org_id] = policy
        logger.info(
            "Policy created", extra={"org_id": policy.org_id}
        )

    def update_policy(self, org_id: str, updates: Dict[str, Any]) -> None:
        """Partial-update a policy.

        Args:
            org_id: Organisation whose policy to update.
            updates: Fields to update.

        Raises:
            PermissionDeniedError: If no policy exists for the org.
        """
        with self._lock:
            policy = self._policies.get(org_id)
            if not policy:
                raise PermissionDeniedError(
                    f"No policy found for org '{org_id}'"
                )
            data = policy.model_dump()
            data.update(updates)
            self._policies[org_id] = OrganizationPolicy(**data)
        logger.info("Policy updated", extra={"org_id": org_id})

    def get_policy(self, org_id: str) -> Optional[OrganizationPolicy]:
        """Retrieve the policy for an organisation.

        Args:
            org_id: Organisation ID.

        Returns:
            The policy, or None if not set.
        """
        return self._policies.get(org_id)

    # ------------------------------------------------------------------
    # Policy enforcement
    # ------------------------------------------------------------------

    def enforce_policy(
        self,
        org_id: str,
        model_name: str,
        estimated_cost: float,
    ) -> Tuple[bool, Optional[str]]:
        """Check a request against the organisation's policy.

        Args:
            org_id: Organisation ID.
            model_name: Model being requested.
            estimated_cost: Estimated cost of the request (USD).

        Returns:
            Tuple of (allowed, rejection_reason).
        """
        policy = self._policies.get(org_id)
        if not policy:
            return True, None

        # 1. Blocked models (takes precedence)
        if model_name in policy.blocked_models:
            return False, f"Model '{model_name}' is blocked by org policy"

        # 2. Allowed models (empty = all allowed)
        if policy.allowed_models and model_name not in policy.allowed_models:
            return False, (
                f"Model '{model_name}' is not in the allowed models list"
            )

        # 3. Per-request cost cap
        if (
            policy.max_cost_per_request is not None
            and estimated_cost > policy.max_cost_per_request
        ):
            return False, (
                f"Estimated cost ${estimated_cost:.4f} exceeds "
                f"per-request limit ${policy.max_cost_per_request:.4f}"
            )

        # 4. Daily budget
        if policy.max_cost_per_day is not None:
            allowed, reason = self.check_budget(org_id, estimated_cost)
            if not allowed:
                return False, reason

        # 5. Daily request count
        if policy.max_requests_per_day is not None:
            count = self._count_requests_today(org_id)
            if count >= policy.max_requests_per_day:
                return False, (
                    f"Daily request limit ({policy.max_requests_per_day}) "
                    f"reached"
                )

        return True, None

    def check_budget(
        self, org_id: str, estimated_cost: float
    ) -> Tuple[bool, Optional[str]]:
        """Check if a cost would exceed the daily budget.

        Args:
            org_id: Organisation ID.
            estimated_cost: Cost to check.

        Returns:
            Tuple of (within_budget, rejection_reason).
        """
        policy = self._policies.get(org_id)
        if not policy or policy.max_cost_per_day is None:
            return True, None

        current_spend = self._daily_spend(org_id)
        if current_spend + estimated_cost > policy.max_cost_per_day:
            return False, (
                f"Daily budget exceeded: current ${current_spend:.4f} + "
                f"estimated ${estimated_cost:.4f} > "
                f"limit ${policy.max_cost_per_day:.4f}"
            )
        return True, None

    def record_spend(self, org_id: str, cost: float) -> None:
        """Record a spend event for budget tracking.

        Args:
            org_id: Organisation ID.
            cost: Cost in USD.
        """
        now = datetime.utcnow()
        with self._lock:
            self._spend_log[org_id].append((now, cost))
            self._request_log[org_id].append(now)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _daily_spend(self, org_id: str) -> float:
        """Sum spend within the budget tracking window.

        Args:
            org_id: Organisation ID.

        Returns:
            Total spend in the window (USD).
        """
        cutoff = datetime.utcnow() - timedelta(
            hours=self._config.budget_tracking_window_hours
        )
        with self._lock:
            entries = self._spend_log.get(org_id, [])
            return sum(cost for ts, cost in entries if ts >= cutoff)

    def _count_requests_today(self, org_id: str) -> int:
        """Count requests within the budget tracking window.

        Args:
            org_id: Organisation ID.

        Returns:
            Number of requests in the window.
        """
        cutoff = datetime.utcnow() - timedelta(
            hours=self._config.budget_tracking_window_hours
        )
        with self._lock:
            timestamps = self._request_log.get(org_id, [])
            return sum(1 for ts in timestamps if ts >= cutoff)
