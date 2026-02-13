"""
Immutable, tamper-evident audit logger with SHA-256 hash chain.

Required for HIPAA, SOC 2, and GDPR compliance.  Each entry
includes a ``prev_hash`` linking it to the prior entry so that
any tampering breaks the chain and is detectable.
"""

import csv
import hashlib
import io
import json
import logging
import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.config import get_settings

logger = logging.getLogger(__name__)


class AuditConfig(BaseModel):
    """Configuration for AuditLogger.

    Attributes:
        storage_dir: Directory for persistent audit files (unused in MVP).
        max_entries_in_memory: Cap on per-org in-memory entries.
        enable_hash_chain: Whether to compute integrity hashes.
    """

    storage_dir: str = Field(default="data/audit")
    max_entries_in_memory: int = Field(default=10_000, ge=100)
    enable_hash_chain: bool = Field(default=True)


class AuditEntry(BaseModel):
    """Single audit-log entry.

    Attributes:
        entry_id: Unique identifier (UUID).
        timestamp: When the action occurred (UTC).
        org_id: Organisation that owns this entry.
        user_id: User who performed the action.
        action: Action type (e.g. ``inference``, ``policy_update``).
        resource: What was acted upon.
        details: Action-specific payload.
        ip_address: Client IP, if available.
        user_agent: Client user-agent, if available.
        result: Outcome of the action.
        data_classification: Sensitivity level.
        prev_hash: SHA-256 hash of the previous entry (integrity chain).
    """

    entry_id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    org_id: str
    user_id: str
    action: str
    resource: str
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    result: Literal["success", "denied", "error"] = "success"
    data_classification: Literal[
        "public", "internal", "confidential", "restricted"
    ] = "internal"
    prev_hash: Optional[str] = None


class AuditLogger:
    """In-memory audit logger with SHA-256 hash chain.

    Args:
        config: Audit configuration.
    """

    def __init__(self, config: Optional[AuditConfig] = None) -> None:
        if config is None:
            _s = get_settings().governance
            config = AuditConfig(
                storage_dir=_s.audit_storage_dir,
                max_entries_in_memory=_s.audit_max_entries,
                enable_hash_chain=_s.audit_enable_hash_chain,
            )
        self._config = config
        self._lock = threading.Lock()
        self._entries: Dict[str, List[AuditEntry]] = defaultdict(list)
        logger.info("AuditLogger initialised", extra={})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(self, entry: AuditEntry) -> None:
        """Append an entry to the org's audit log.

        If hash chaining is enabled, ``prev_hash`` is computed from
        the most recent entry for the same ``org_id``.

        Args:
            entry: The audit entry to record.
        """
        with self._lock:
            org_entries = self._entries[entry.org_id]
            if self._config.enable_hash_chain:
                if org_entries:
                    entry.prev_hash = self._hash_entry(org_entries[-1])
                else:
                    entry.prev_hash = None
            org_entries.append(entry)
            if len(org_entries) > self._config.max_entries_in_memory:
                org_entries.pop(0)
        logger.info(
            "Audit entry logged",
            extra={
                "entry_id": entry.entry_id,
                "org_id": entry.org_id,
                "action": entry.action,
            },
        )

    def query(
        self,
        org_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query audit entries for an organisation.

        Args:
            org_id: Organisation ID to query.
            start_time: Include entries at or after this time.
            end_time: Include entries at or before this time.
            action: Filter by action type.
            user_id: Filter by user ID.
            limit: Maximum entries to return.

        Returns:
            List of matching entries (newest first).
        """
        with self._lock:
            entries = list(self._entries.get(org_id, []))

        results: List[AuditEntry] = []
        for entry in reversed(entries):
            if start_time and entry.timestamp < start_time:
                continue
            if end_time and entry.timestamp > end_time:
                continue
            if action and entry.action != action:
                continue
            if user_id and entry.user_id != user_id:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def export(
        self,
        org_id: str,
        format: Literal["json", "csv"] = "json",
    ) -> bytes:
        """Export all audit entries for an organisation.

        Args:
            org_id: Organisation ID.
            format: Output format (``json`` or ``csv``).

        Returns:
            Serialised bytes in the requested format.
        """
        with self._lock:
            entries = list(self._entries.get(org_id, []))

        if format == "json":
            data = [e.model_dump(mode="json") for e in entries]
            return json.dumps(data, indent=2, default=str).encode("utf-8")

        # CSV
        buf = io.StringIO()
        fieldnames = list(AuditEntry.model_fields.keys())
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row = entry.model_dump(mode="json")
            row["details"] = json.dumps(row["details"])
            writer.writerow(row)
        return buf.getvalue().encode("utf-8")

    def verify_integrity(self, org_id: str) -> bool:
        """Verify the hash chain for an organisation's audit log.

        Recomputes each ``prev_hash`` from scratch and checks it
        matches the stored value.

        Args:
            org_id: Organisation ID to verify.

        Returns:
            True if the chain is intact, False if tampered.
        """
        with self._lock:
            entries = list(self._entries.get(org_id, []))

        if not entries:
            return True

        if entries[0].prev_hash is not None:
            return False

        for i in range(1, len(entries)):
            expected = self._hash_entry(entries[i - 1])
            if entries[i].prev_hash != expected:
                logger.warning(
                    "Audit chain integrity failure",
                    extra={
                        "org_id": org_id,
                        "entry_index": i,
                        "entry_id": entries[i].entry_id,
                    },
                )
                return False
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_entry(entry: AuditEntry) -> str:
        """Compute SHA-256 of an entry (excluding prev_hash).

        Args:
            entry: Audit entry to hash.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        data = entry.model_dump(mode="json", exclude={"prev_hash"})
        canonical = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
