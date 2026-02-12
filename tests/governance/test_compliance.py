"""Tests for ComplianceManager (HIPAA/SOC2/GDPR/PCI/CCPA + PII redaction)."""

import pytest

from src.exceptions import ComplianceViolationError
from src.governance.audit import AuditLogger
from src.governance.compliance import (
    ComplianceConfig,
    ComplianceManager,
    ComplianceProfile,
)


@pytest.fixture
def manager() -> ComplianceManager:
    return ComplianceManager()


@pytest.fixture
def manager_with_audit() -> ComplianceManager:
    return ComplianceManager(audit_logger=AuditLogger())


def _hipaa_profile(org_id: str = "org-1", **overrides: object) -> ComplianceProfile:
    defaults = dict(
        org_id=org_id,
        frameworks=["hipaa"],
        encryption_required=True,
        prompt_storage_allowed=False,
        pii_detection_enabled=True,
    )
    defaults.update(overrides)
    return ComplianceProfile(**defaults)  # type: ignore[arg-type]


def _gdpr_profile(org_id: str = "org-1", **overrides: object) -> ComplianceProfile:
    defaults = dict(
        org_id=org_id,
        frameworks=["gdpr"],
        data_residency="eu",
        retention_days=365,
    )
    defaults.update(overrides)
    return ComplianceProfile(**defaults)  # type: ignore[arg-type]


# ── HIPAA checks ───────────────────────────────────────


class TestHIPAA:
    def test_compliant_request(self, manager: ComplianceManager) -> None:
        manager.register_profile(_hipaa_profile())
        ok, violations = manager.check_request(
            "org-1", "claude-3-5-sonnet", "What is 2+2?"
        )
        assert ok
        assert violations == []

    def test_encryption_not_enabled(self, manager: ComplianceManager) -> None:
        manager.register_profile(_hipaa_profile(encryption_required=False))
        ok, violations = manager.check_request("org-1", "gpt-4-turbo", "hi")
        assert not ok
        assert any("encryption" in v for v in violations)

    def test_prompt_storage_enabled(self, manager: ComplianceManager) -> None:
        manager.register_profile(_hipaa_profile(prompt_storage_allowed=True))
        ok, violations = manager.check_request("org-1", "gpt-4-turbo", "hi")
        assert not ok
        assert any("prompt storage" in v for v in violations)

    def test_pii_detection_disabled(self, manager: ComplianceManager) -> None:
        manager.register_profile(_hipaa_profile(pii_detection_enabled=False))
        ok, violations = manager.check_request("org-1", "gpt-4-turbo", "hi")
        assert not ok
        assert any("PII detection" in v for v in violations)

    def test_pii_in_prompt_detected(self, manager: ComplianceManager) -> None:
        manager.register_profile(_hipaa_profile())
        ok, violations = manager.check_request(
            "org-1", "gpt-4-turbo", "Patient SSN is 123-45-6789"
        )
        assert not ok
        assert any("PII detected" in v for v in violations)


# ── GDPR checks ───────────────────────────────────────


class TestGDPR:
    def test_compliant_request(self, manager: ComplianceManager) -> None:
        manager.register_profile(_gdpr_profile())
        ok, violations = manager.check_request(
            "org-1", "mistral-large", "Summarise this document"
        )
        assert ok

    def test_wrong_data_residency(self, manager: ComplianceManager) -> None:
        manager.register_profile(_gdpr_profile())
        ok, violations = manager.check_request(
            "org-1", "gpt-4-turbo", "query"
        )
        assert not ok
        assert any("region" in v for v in violations)

    def test_retention_exceeds_limit(self, manager: ComplianceManager) -> None:
        manager.register_profile(_gdpr_profile(retention_days=730))
        ok, violations = manager.check_request(
            "org-1", "mistral-large", "query"
        )
        assert not ok
        assert any("retention" in v for v in violations)


# ── PCI-DSS checks ────────────────────────────────────


class TestPCIDSS:
    def test_encryption_required(self, manager: ComplianceManager) -> None:
        profile = ComplianceProfile(
            org_id="org-pci",
            frameworks=["pci_dss"],
            encryption_required=False,
        )
        manager.register_profile(profile)
        ok, violations = manager.check_request("org-pci", "gpt-4-turbo", "hi")
        assert not ok
        assert any("PCI-DSS" in v for v in violations)

    def test_encryption_present(self, manager: ComplianceManager) -> None:
        profile = ComplianceProfile(
            org_id="org-pci",
            frameworks=["pci_dss"],
            encryption_required=True,
        )
        manager.register_profile(profile)
        ok, violations = manager.check_request("org-pci", "gpt-4-turbo", "hi")
        assert ok


# ── CCPA checks ────────────────────────────────────────


class TestCCPA:
    def test_pii_detection_required(self, manager: ComplianceManager) -> None:
        profile = ComplianceProfile(
            org_id="org-ccpa",
            frameworks=["ccpa"],
            pii_detection_enabled=False,
        )
        manager.register_profile(profile)
        ok, violations = manager.check_request("org-ccpa", "gpt-4-turbo", "hi")
        assert not ok
        assert any("CCPA" in v for v in violations)


# ── PII Redaction ──────────────────────────────────────


class TestRedactPII:
    def test_email(self, manager: ComplianceManager) -> None:
        text = "Contact john@example.com for info"
        redacted, types = manager.redact_pii(text)
        assert "[EMAIL_REDACTED]" in redacted
        assert "email" in types

    def test_ssn(self, manager: ComplianceManager) -> None:
        text = "SSN: 123-45-6789"
        redacted, types = manager.redact_pii(text)
        assert "[SSN_REDACTED]" in redacted
        assert "ssn" in types

    def test_credit_card(self, manager: ComplianceManager) -> None:
        text = "Card: 4111-1111-1111-1111"
        redacted, types = manager.redact_pii(text)
        assert "[CC_REDACTED]" in redacted
        assert "credit_card" in types

    def test_ip_address(self, manager: ComplianceManager) -> None:
        text = "Server IP: 192.168.1.100"
        redacted, types = manager.redact_pii(text)
        assert "[IP_REDACTED]" in redacted
        assert "ip_address" in types

    def test_phone(self, manager: ComplianceManager) -> None:
        text = "Call +1 (555) 123-4567 now"
        redacted, types = manager.redact_pii(text)
        assert "[PHONE_REDACTED]" in redacted
        assert "phone" in types

    def test_no_pii(self, manager: ComplianceManager) -> None:
        text = "This is a clean text with no PII"
        redacted, types = manager.redact_pii(text)
        assert redacted == text
        assert types == []

    def test_multiple_pii_types(self, manager: ComplianceManager) -> None:
        text = "Email: user@test.com, SSN: 111-22-3333"
        redacted, types = manager.redact_pii(text)
        assert "[EMAIL_REDACTED]" in redacted
        assert "[SSN_REDACTED]" in redacted
        assert len(types) >= 2


# ── Data Residency ─────────────────────────────────────


class TestDataResidency:
    def test_matching_region(self, manager: ComplianceManager) -> None:
        assert manager.check_data_residency("gpt-4-turbo", "us") is True

    def test_wrong_region(self, manager: ComplianceManager) -> None:
        assert manager.check_data_residency("gpt-4-turbo", "eu") is False

    def test_eu_model_in_eu(self, manager: ComplianceManager) -> None:
        assert manager.check_data_residency("mistral-large", "eu") is True

    def test_unknown_model(self, manager: ComplianceManager) -> None:
        assert manager.check_data_residency("unknown-model", "us") is False


# ── Compliance Reports ─────────────────────────────────


class TestComplianceReports:
    def test_hipaa_report_compliant(
        self, manager_with_audit: ComplianceManager
    ) -> None:
        manager_with_audit.register_profile(_hipaa_profile())
        report = manager_with_audit.generate_compliance_report("org-1", "hipaa")
        assert report["overall_status"] == "compliant"
        assert report["checks_passed"] == report["checks_total"]

    def test_hipaa_report_non_compliant(
        self, manager: ComplianceManager
    ) -> None:
        manager.register_profile(
            _hipaa_profile(encryption_required=False)
        )
        report = manager.generate_compliance_report("org-1", "hipaa")
        assert report["overall_status"] == "non_compliant"

    def test_gdpr_report(self, manager: ComplianceManager) -> None:
        manager.register_profile(_gdpr_profile())
        report = manager.generate_compliance_report("org-1", "gdpr")
        assert "checks" in report
        assert report["framework"] == "gdpr"

    def test_report_no_profile_raises(self, manager: ComplianceManager) -> None:
        with pytest.raises(ComplianceViolationError):
            manager.generate_compliance_report("no-org", "hipaa")

    def test_no_profile_passes_request(self, manager: ComplianceManager) -> None:
        ok, violations = manager.check_request("no-org", "any-model", "hi")
        assert ok
        assert violations == []

    def test_retention_enforcement(self, manager: ComplianceManager) -> None:
        manager.register_profile(_hipaa_profile())
        deleted = manager.enforce_retention("org-1")
        assert deleted == 0  # MVP placeholder
