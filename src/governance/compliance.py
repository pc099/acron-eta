"""
Compliance manager for regulatory framework enforcement.

Enforces HIPAA, SOC 2, GDPR, PCI-DSS, and CCPA requirements
including PII detection/redaction, data residency checks,
retention policies, and compliance report generation.
"""

import logging
import re
import threading
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field

from src.config import get_settings
from src.exceptions import ComplianceViolationError
from src.governance.audit import AuditLogger

logger = logging.getLogger(__name__)

# ── PII regex patterns (ordered specific → general) ───

_PII_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    (
        "credit_card",
        re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    ),
    (
        "ssn",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    ),
    (
        "email",
        re.compile(r"\b[\w.+-]+@[\w.-]+\.\w{2,}\b"),
    ),
    (
        "ip_address",
        re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),
    ),
    (
        "phone",
        re.compile(r"\+?[\d\s\-()]{10,}"),
    ),
]

_PII_REPLACEMENTS: Dict[str, str] = {
    "credit_card": "[CC_REDACTED]",
    "ssn": "[SSN_REDACTED]",
    "email": "[EMAIL_REDACTED]",
    "ip_address": "[IP_REDACTED]",
    "phone": "[PHONE_REDACTED]",
}


# ── Data Models ────────────────────────────────────────


class ComplianceConfig(BaseModel):
    """Configuration for ComplianceManager.

    Attributes:
        pii_detection_enabled: Global toggle for PII detection.
        default_retention_days: Default data retention period.
        model_region_map: Mapping of model names to their data regions.
    """

    pii_detection_enabled: bool = Field(
        default_factory=lambda: get_settings().governance.compliance_pii_detection
    )
    default_retention_days: int = Field(
        default_factory=lambda: get_settings().governance.compliance_default_retention_days, ge=1
    )
    model_region_map: Dict[str, str] = Field(
        default_factory=lambda: {
            "gpt-4-turbo": "us",
            "gpt-4": "us",
            "claude-opus-4": "us",
            "claude-3-5-sonnet": "us",
            "mistral-large": "eu",
        }
    )


class ComplianceProfile(BaseModel):
    """Per-organisation compliance profile.

    Attributes:
        org_id: Organisation identifier.
        frameworks: Active compliance frameworks.
        data_residency: Required data region (e.g. ``us``, ``eu``).
        encryption_required: Whether encryption at rest is mandatory.
        prompt_storage_allowed: Whether prompts may be stored/cached.
        retention_days: Data retention period in days.
        pii_detection_enabled: Whether PII scanning is active.
    """

    org_id: str
    frameworks: List[
        Literal["hipaa", "soc2", "gdpr", "pci_dss", "ccpa"]
    ] = Field(default_factory=list)
    data_residency: Optional[str] = None
    encryption_required: bool = False
    prompt_storage_allowed: bool = True
    retention_days: int = Field(default=365, ge=1)
    pii_detection_enabled: bool = False


class ComplianceManager:
    """Enforce compliance requirements per organisation profile.

    Args:
        config: Compliance configuration.
        audit_logger: Optional audit logger for compliance events.
    """

    def __init__(
        self,
        config: Optional[ComplianceConfig] = None,
        audit_logger: Optional[AuditLogger] = None,
    ) -> None:
        self._config = config or ComplianceConfig()
        self._audit_logger = audit_logger
        self._lock = threading.Lock()
        self._profiles: Dict[str, ComplianceProfile] = {}
        logger.info("ComplianceManager initialised", extra={})

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def register_profile(self, profile: ComplianceProfile) -> None:
        """Register or replace a compliance profile.

        Args:
            profile: The compliance profile to store.
        """
        with self._lock:
            self._profiles[profile.org_id] = profile
        logger.info(
            "Compliance profile registered",
            extra={"org_id": profile.org_id, "frameworks": profile.frameworks},
        )

    def get_profile(self, org_id: str) -> Optional[ComplianceProfile]:
        """Retrieve a compliance profile.

        Args:
            org_id: Organisation ID.

        Returns:
            The profile, or None if not registered.
        """
        return self._profiles.get(org_id)

    # ------------------------------------------------------------------
    # Request compliance check
    # ------------------------------------------------------------------

    def check_request(
        self,
        org_id: str,
        model_name: str,
        prompt: str,
    ) -> Tuple[bool, List[str]]:
        """Check an inference request against compliance requirements.

        Args:
            org_id: Organisation ID.
            model_name: Model being requested.
            prompt: The prompt text.

        Returns:
            Tuple of (compliant, list_of_violations).
        """
        profile = self._profiles.get(org_id)
        if not profile:
            return True, []

        violations: List[str] = []

        for framework in profile.frameworks:
            fw_violations = self._check_framework(
                framework, profile, model_name, prompt
            )
            violations.extend(fw_violations)

        compliant = len(violations) == 0
        if not compliant:
            logger.warning(
                "Compliance violations detected",
                extra={"org_id": org_id, "violations": violations},
            )
        return compliant, violations

    # ------------------------------------------------------------------
    # PII detection and redaction
    # ------------------------------------------------------------------

    def redact_pii(self, text: str) -> Tuple[str, List[str]]:
        """Detect and redact PII from text.

        Args:
            text: Input text to scan.

        Returns:
            Tuple of (redacted_text, list_of_pii_types_found).
        """
        pii_types_found: List[str] = []
        redacted = text

        for pii_type, pattern in _PII_PATTERNS:
            if pattern.search(redacted):
                if pii_type not in pii_types_found:
                    pii_types_found.append(pii_type)
                redacted = pattern.sub(_PII_REPLACEMENTS[pii_type], redacted)

        return redacted, pii_types_found

    # ------------------------------------------------------------------
    # Data residency
    # ------------------------------------------------------------------

    def check_data_residency(
        self, model_name: str, required_region: str
    ) -> bool:
        """Check if a model's data region matches the requirement.

        Args:
            model_name: Model name to check.
            required_region: Required data region (e.g. ``us``, ``eu``).

        Returns:
            True if the model is in the required region.
        """
        model_region = self._config.model_region_map.get(model_name)
        if model_region is None:
            # Unknown model region — conservative: deny
            return False
        return model_region == required_region

    # ------------------------------------------------------------------
    # Retention enforcement
    # ------------------------------------------------------------------

    def enforce_retention(self, org_id: str) -> int:
        """Delete data older than the profile's retention period.

        Args:
            org_id: Organisation ID.

        Returns:
            Number of records deleted (0 in MVP — placeholder).
        """
        profile = self._profiles.get(org_id)
        if not profile:
            return 0

        cutoff = datetime.utcnow()
        logger.info(
            "Retention enforcement executed",
            extra={
                "org_id": org_id,
                "retention_days": profile.retention_days,
                "cutoff": cutoff.isoformat(),
            },
        )
        # MVP: in-memory only, no persistent storage to purge
        return 0

    # ------------------------------------------------------------------
    # Compliance reports
    # ------------------------------------------------------------------

    def generate_compliance_report(
        self, org_id: str, framework: str
    ) -> Dict[str, Any]:
        """Generate a compliance status report.

        Args:
            org_id: Organisation ID.
            framework: Framework to report on.

        Returns:
            Report dictionary with checks and overall status.

        Raises:
            ComplianceViolationError: If the org has no compliance profile.
        """
        profile = self._profiles.get(org_id)
        if not profile:
            raise ComplianceViolationError(
                f"No compliance profile for org '{org_id}'"
            )

        checks = self._framework_checks(framework, profile)
        passed = sum(1 for c in checks if c["status"] == "pass")
        total = len(checks)

        return {
            "org_id": org_id,
            "framework": framework,
            "generated_at": datetime.utcnow().isoformat(),
            "overall_status": "compliant" if passed == total else "non_compliant",
            "checks_passed": passed,
            "checks_total": total,
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # Internal: framework-specific checks
    # ------------------------------------------------------------------

    def _check_framework(
        self,
        framework: str,
        profile: ComplianceProfile,
        model_name: str,
        prompt: str,
    ) -> List[str]:
        """Run framework-specific violation checks.

        Args:
            framework: Framework name.
            profile: The org's compliance profile.
            model_name: Requested model.
            prompt: The prompt text.

        Returns:
            List of violation descriptions.
        """
        violations: List[str] = []

        if framework == "hipaa":
            if not profile.encryption_required:
                violations.append("HIPAA: encryption at rest is required")
            if profile.prompt_storage_allowed:
                violations.append(
                    "HIPAA: prompt storage must be disabled"
                )
            if not profile.pii_detection_enabled:
                violations.append("HIPAA: PII detection must be enabled")
            # Check for PII in prompt when detection is enabled
            if profile.pii_detection_enabled:
                _, pii_found = self.redact_pii(prompt)
                if pii_found:
                    violations.append(
                        f"HIPAA: PII detected in prompt ({', '.join(pii_found)})"
                    )

        elif framework == "soc2":
            # SOC 2 requires audit logging — checked at profile level
            pass

        elif framework == "gdpr":
            if profile.data_residency:
                if not self.check_data_residency(
                    model_name, profile.data_residency
                ):
                    violations.append(
                        f"GDPR: model '{model_name}' is not in "
                        f"required region '{profile.data_residency}'"
                    )
            if profile.retention_days > 365:
                violations.append(
                    "GDPR: retention period exceeds 365 days"
                )

        elif framework == "pci_dss":
            if not profile.encryption_required:
                violations.append("PCI-DSS: encryption is required")

        elif framework == "ccpa":
            if not profile.pii_detection_enabled:
                violations.append("CCPA: PII detection must be enabled")

        return violations

    def _framework_checks(
        self, framework: str, profile: ComplianceProfile
    ) -> List[Dict[str, str]]:
        """Generate detailed check results for a report.

        Args:
            framework: Framework name.
            profile: The org's compliance profile.

        Returns:
            List of check result dicts.
        """
        checks: List[Dict[str, str]] = []

        if framework == "hipaa":
            checks.append({
                "check": "encryption_at_rest",
                "status": "pass" if profile.encryption_required else "fail",
                "detail": "Data encryption at rest",
            })
            checks.append({
                "check": "prompt_storage_disabled",
                "status": "pass" if not profile.prompt_storage_allowed else "fail",
                "detail": "Prompt/response storage prohibited",
            })
            checks.append({
                "check": "pii_detection",
                "status": "pass" if profile.pii_detection_enabled else "fail",
                "detail": "PII detection and redaction enabled",
            })
            checks.append({
                "check": "audit_logging",
                "status": "pass" if self._audit_logger is not None else "fail",
                "detail": "Audit logging active",
            })

        elif framework == "soc2":
            checks.append({
                "check": "audit_trail",
                "status": "pass" if self._audit_logger is not None else "fail",
                "detail": "Access control audit trail",
            })

        elif framework == "gdpr":
            checks.append({
                "check": "data_residency",
                "status": "pass" if profile.data_residency else "fail",
                "detail": "Data residency configured",
            })
            checks.append({
                "check": "retention_policy",
                "status": "pass" if profile.retention_days <= 365 else "fail",
                "detail": f"Retention period: {profile.retention_days} days",
            })

        elif framework == "pci_dss":
            checks.append({
                "check": "encryption",
                "status": "pass" if profile.encryption_required else "fail",
                "detail": "Encryption required for card data",
            })

        elif framework == "ccpa":
            checks.append({
                "check": "pii_detection",
                "status": "pass" if profile.pii_detection_enabled else "fail",
                "detail": "PII detection enabled",
            })

        return checks
