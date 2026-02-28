"""Audit logging helper — writes immutable AuditLog records.

Usage:
    await write_audit(db, org_id=..., user_id=..., action="key.created",
                      resource_type="api_key", resource_id=str(key.id))
"""

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: Optional[uuid.UUID] = None,
    action: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Insert an immutable audit log entry."""
    entry = AuditLog(
        id=uuid.uuid4(),
        organisation_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        metadata_=metadata,
    )
    db.add(entry)
