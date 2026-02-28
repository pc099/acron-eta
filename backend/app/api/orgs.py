"""Organisation routes — CRUD + membership management.

All endpoints require JWT auth and membership verification.
Non-members get 403. Viewers cannot mutate.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import (
    Invitation,
    Member,
    MemberRole,
    Organisation,
    RequestLog,
    User,
)
from app.services.audit import write_audit

router = APIRouter()


# ── Pydantic schemas ──────────────────────────


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    monthly_request_limit: int
    monthly_token_limit: int
    created_at: datetime


class OrgUpdateRequest(BaseModel):
    name: Optional[str] = None


class MemberResponse(BaseModel):
    user_id: str
    email: str
    name: Optional[str]
    role: str
    joined_at: datetime


class InviteMemberRequest(BaseModel):
    email: str
    role: str = "member"


class UpdateRoleRequest(BaseModel):
    role: str


class UsageResponse(BaseModel):
    period_start: datetime
    total_requests: int
    total_input_tokens: int
    total_output_tokens: int
    monthly_request_limit: int
    monthly_token_limit: int
    requests_pct: float
    tokens_pct: float


# ── Helpers ───────────────────────────────────


def _require_org(request: Request) -> str:
    """Extract and validate org_id from request state."""
    org_id = getattr(request.state, "org_id", None)
    if not org_id:
        raise HTTPException(status_code=403, detail="Organisation context required")
    return org_id


def _require_role(request: Request, min_roles: set[MemberRole]) -> MemberRole:
    """Ensure the authenticated user has one of the required roles."""
    role = getattr(request.state, "role", None)
    if role not in min_roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return role


# ── Routes ────────────────────────────────────


@router.get("/{slug}", response_model=OrgResponse)
async def get_org(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get organisation details by slug."""
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan.value,
        monthly_request_limit=org.monthly_request_limit,
        monthly_token_limit=org.monthly_token_limit,
        created_at=org.created_at,
    )


@router.patch("/{slug}", response_model=OrgResponse)
async def update_org(
    slug: str, body: OrgUpdateRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Update organisation name/settings. Requires admin+ role."""
    _require_role(request, {MemberRole.OWNER, MemberRole.ADMIN})

    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    if body.name is not None:
        org.name = body.name

    await db.flush()

    user_id = getattr(request.state, "user_id", None)
    await write_audit(
        db, org_id=org.id,
        user_id=uuid.UUID(user_id) if user_id else None,
        action="org.updated", resource_type="organisation",
        resource_id=str(org.id),
        ip_address=request.client.host if request.client else None,
    )

    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        plan=org.plan.value,
        monthly_request_limit=org.monthly_request_limit,
        monthly_token_limit=org.monthly_token_limit,
        created_at=org.created_at,
    )


@router.get("/{slug}/members", response_model=list[MemberResponse])
async def list_members(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """List all members of an organisation."""
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    members_result = await db.execute(
        select(Member).where(Member.organisation_id == org.id)
    )
    members = members_result.scalars().all()

    response = []
    for m in members:
        user = await db.get(User, m.user_id)
        if user:
            response.append(
                MemberResponse(
                    user_id=str(user.id),
                    email=user.email,
                    name=user.name,
                    role=m.role.value,
                    joined_at=m.created_at,
                )
            )

    return response


@router.post("/{slug}/members", status_code=201)
async def invite_member(
    slug: str, body: InviteMemberRequest, request: Request, db: AsyncSession = Depends(get_db)
):
    """Invite a new member to the organisation. Requires admin+ role."""
    _require_role(request, {MemberRole.OWNER, MemberRole.ADMIN})
    user_id = getattr(request.state, "user_id", None)

    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    # Check if user is already a member
    existing_user = await db.execute(
        select(User).where(User.email == body.email)
    )
    existing = existing_user.scalar_one_or_none()
    if existing:
        existing_member = await db.execute(
            select(Member).where(
                Member.organisation_id == org.id,
                Member.user_id == existing.id,
            )
        )
        if existing_member.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="User is already a member")

    # Create invitation
    invitation = Invitation(
        id=uuid.uuid4(),
        organisation_id=org.id,
        invited_by_user_id=uuid.UUID(user_id) if user_id else uuid.uuid4(),
        email=body.email,
        role=MemberRole(body.role),
        token=secrets.token_urlsafe(48),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    await db.flush()

    await write_audit(
        db, org_id=org.id,
        user_id=uuid.UUID(user_id) if user_id else None,
        action="member.invited", resource_type="invitation",
        resource_id=str(invitation.id),
        ip_address=request.client.host if request.client else None,
        metadata={"email": body.email, "role": body.role},
    )

    return {
        "invitation_id": str(invitation.id),
        "email": body.email,
        "role": body.role,
        "expires_at": invitation.expires_at.isoformat(),
    }


@router.patch("/{slug}/members/{member_user_id}")
async def update_member_role(
    slug: str,
    member_user_id: str,
    body: UpdateRoleRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update a member's role. Only owners can change roles."""
    _require_role(request, {MemberRole.OWNER})

    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    member_result = await db.execute(
        select(Member).where(
            Member.organisation_id == org.id,
            Member.user_id == uuid.UUID(member_user_id),
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    old_role = member.role.value
    member.role = MemberRole(body.role)
    await db.flush()

    acting_user_id = getattr(request.state, "user_id", None)
    await write_audit(
        db, org_id=org.id,
        user_id=uuid.UUID(acting_user_id) if acting_user_id else None,
        action="member.role_changed", resource_type="member",
        resource_id=member_user_id,
        ip_address=request.client.host if request.client else None,
        metadata={"old_role": old_role, "new_role": body.role},
    )

    return {"user_id": member_user_id, "role": body.role}


@router.delete("/{slug}/members/{member_user_id}", status_code=204)
async def remove_member(
    slug: str, member_user_id: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """Remove a member. Requires admin+ role. Cannot remove owner."""
    _require_role(request, {MemberRole.OWNER, MemberRole.ADMIN})

    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    member_result = await db.execute(
        select(Member).where(
            Member.organisation_id == org.id,
            Member.user_id == uuid.UUID(member_user_id),
        )
    )
    member = member_result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    if member.role == MemberRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot remove the owner")

    acting_user_id = getattr(request.state, "user_id", None)
    await write_audit(
        db, org_id=org.id,
        user_id=uuid.UUID(acting_user_id) if acting_user_id else None,
        action="member.removed", resource_type="member",
        resource_id=member_user_id,
        ip_address=request.client.host if request.client else None,
    )

    await db.delete(member)
    await db.flush()


@router.post("/invitations/{token}/accept")
async def accept_invitation(
    token: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """Accept an invitation to join an organisation. Requires JWT auth."""
    user_id_str = getattr(request.state, "user_id", None)
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Authentication required")

    result = await db.execute(
        select(Invitation).where(Invitation.token == token)
    )
    invitation = result.scalar_one_or_none()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invitation already accepted")

    now = datetime.now(timezone.utc)
    if invitation.expires_at < now:
        raise HTTPException(status_code=410, detail="Invitation has expired")

    # Look up the accepting user
    user_id = uuid.UUID(user_id_str)
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check email matches invitation
    if user.email != invitation.email:
        raise HTTPException(status_code=403, detail="Invitation was sent to a different email")

    # Check not already a member
    existing = await db.execute(
        select(Member).where(
            Member.organisation_id == invitation.organisation_id,
            Member.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Already a member of this organisation")

    # Create membership
    member = Member(
        organisation_id=invitation.organisation_id,
        user_id=user_id,
        role=invitation.role,
    )
    db.add(member)

    # Mark invitation as accepted
    invitation.accepted_at = now
    await db.flush()

    # Get org slug for redirect
    org = await db.get(Organisation, invitation.organisation_id)

    await write_audit(
        db, org_id=invitation.organisation_id,
        user_id=user_id,
        action="member.joined", resource_type="invitation",
        resource_id=str(invitation.id),
        ip_address=request.client.host if request.client else None,
    )

    return {
        "org_id": str(invitation.organisation_id),
        "org_slug": org.slug if org else None,
        "role": invitation.role.value,
    }


@router.get("/{slug}/usage", response_model=UsageResponse)
async def get_usage(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get current period usage vs limits for the org."""
    result = await db.execute(
        select(Organisation).where(Organisation.slug == slug)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    # Current month start
    now = datetime.now(timezone.utc)
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Aggregate from request_logs
    usage_result = await db.execute(
        select(
            func.count(RequestLog.id).label("total_requests"),
            func.coalesce(func.sum(RequestLog.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(RequestLog.output_tokens), 0).label("total_output_tokens"),
        ).where(
            RequestLog.organisation_id == org.id,
            RequestLog.created_at >= period_start,
        )
    )
    row = usage_result.one()

    total_requests = row.total_requests or 0
    total_input = row.total_input_tokens or 0
    total_output = row.total_output_tokens or 0
    total_tokens = total_input + total_output

    req_pct = (total_requests / org.monthly_request_limit * 100) if org.monthly_request_limit > 0 else 0
    tok_pct = (total_tokens / org.monthly_token_limit * 100) if org.monthly_token_limit > 0 else 0

    return UsageResponse(
        period_start=period_start,
        total_requests=total_requests,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        monthly_request_limit=org.monthly_request_limit,
        monthly_token_limit=org.monthly_token_limit,
        requests_pct=round(req_pct, 1),
        tokens_pct=round(tok_pct, 1),
    )
