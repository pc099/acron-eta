"""Tests for AuditLogger (hash-chain audit trail)."""

import json
from datetime import datetime, timedelta

import pytest

from src.governance.audit import AuditConfig, AuditEntry, AuditLogger


@pytest.fixture
def audit_logger() -> AuditLogger:
    return AuditLogger()


def _make_entry(
    org_id: str = "org-1",
    user_id: str = "user-1",
    action: str = "inference",
    **kwargs: object,
) -> AuditEntry:
    return AuditEntry(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource="model/claude-3-5-sonnet",
        details={"prompt_length": 42},
        result="success",
        data_classification="internal",
        **kwargs,  # type: ignore[arg-type]
    )


# ── Logging ────────────────────────────────────────────


class TestLog:
    def test_log_single_entry(self, audit_logger: AuditLogger) -> None:
        entry = _make_entry()
        audit_logger.log(entry)
        results = audit_logger.query("org-1")
        assert len(results) == 1
        assert results[0].entry_id == entry.entry_id

    def test_log_sets_prev_hash_chain(self, audit_logger: AuditLogger) -> None:
        e1 = _make_entry()
        e2 = _make_entry()
        audit_logger.log(e1)
        audit_logger.log(e2)

        results = audit_logger.query("org-1")
        # Newest first
        assert results[0].prev_hash is not None
        assert results[1].prev_hash is None

    def test_log_different_orgs_isolated(
        self, audit_logger: AuditLogger
    ) -> None:
        audit_logger.log(_make_entry(org_id="org-a"))
        audit_logger.log(_make_entry(org_id="org-b"))

        assert len(audit_logger.query("org-a")) == 1
        assert len(audit_logger.query("org-b")) == 1

    def test_max_entries_cap(self) -> None:
        cfg = AuditConfig(max_entries_in_memory=100)
        al = AuditLogger(config=cfg)
        for _ in range(150):
            al.log(_make_entry())
        assert len(al.query("org-1", limit=200)) == 100


# ── Querying ───────────────────────────────────────────


class TestQuery:
    def test_filter_by_action(self, audit_logger: AuditLogger) -> None:
        audit_logger.log(_make_entry(action="inference"))
        audit_logger.log(_make_entry(action="policy_update"))
        audit_logger.log(_make_entry(action="inference"))

        results = audit_logger.query("org-1", action="inference")
        assert len(results) == 2

    def test_filter_by_user_id(self, audit_logger: AuditLogger) -> None:
        audit_logger.log(_make_entry(user_id="alice"))
        audit_logger.log(_make_entry(user_id="bob"))

        results = audit_logger.query("org-1", user_id="alice")
        assert len(results) == 1
        assert results[0].user_id == "alice"

    def test_filter_by_time_range(self, audit_logger: AuditLogger) -> None:
        now = datetime.utcnow()
        old = _make_entry()
        old.timestamp = now - timedelta(hours=2)
        recent = _make_entry()
        recent.timestamp = now

        audit_logger.log(old)
        audit_logger.log(recent)

        results = audit_logger.query(
            "org-1",
            start_time=now - timedelta(hours=1),
        )
        assert len(results) == 1

    def test_limit(self, audit_logger: AuditLogger) -> None:
        for _ in range(20):
            audit_logger.log(_make_entry())
        results = audit_logger.query("org-1", limit=5)
        assert len(results) == 5

    def test_query_empty_org(self, audit_logger: AuditLogger) -> None:
        results = audit_logger.query("nonexistent")
        assert results == []


# ── Export ─────────────────────────────────────────────


class TestExport:
    def test_export_json(self, audit_logger: AuditLogger) -> None:
        audit_logger.log(_make_entry())
        audit_logger.log(_make_entry())

        data = json.loads(audit_logger.export("org-1", format="json"))
        assert isinstance(data, list)
        assert len(data) == 2
        assert "entry_id" in data[0]

    def test_export_csv(self, audit_logger: AuditLogger) -> None:
        audit_logger.log(_make_entry())

        csv_bytes = audit_logger.export("org-1", format="csv")
        lines = csv_bytes.decode("utf-8").strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert "entry_id" in lines[0]

    def test_export_empty_org(self, audit_logger: AuditLogger) -> None:
        data = json.loads(audit_logger.export("empty-org", format="json"))
        assert data == []


# ── Integrity ──────────────────────────────────────────


class TestVerifyIntegrity:
    def test_intact_chain(self, audit_logger: AuditLogger) -> None:
        for _ in range(5):
            audit_logger.log(_make_entry())
        assert audit_logger.verify_integrity("org-1") is True

    def test_tampered_chain_detected(self, audit_logger: AuditLogger) -> None:
        for _ in range(5):
            audit_logger.log(_make_entry())

        # Tamper with an entry's action field
        audit_logger._entries["org-1"][2].action = "TAMPERED"
        assert audit_logger.verify_integrity("org-1") is False

    def test_empty_org_is_valid(self, audit_logger: AuditLogger) -> None:
        assert audit_logger.verify_integrity("empty") is True

    def test_single_entry_valid(self, audit_logger: AuditLogger) -> None:
        audit_logger.log(_make_entry())
        assert audit_logger.verify_integrity("org-1") is True

    def test_hash_chain_disabled(self) -> None:
        cfg = AuditConfig(enable_hash_chain=False)
        al = AuditLogger(config=cfg)
        al.log(_make_entry())
        al.log(_make_entry())
        # prev_hash remains None when disabled
        entries = al.query("org-1")
        assert all(e.prev_hash is None for e in entries)
