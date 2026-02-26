"""Auth routes — signup and login.

POST /auth/signup — Creates a user + default organisation + owner membership.
POST /auth/login  — Looks up user by Clerk ID, returns user + orgs.
POST /auth/webhook — Clerk webhook handler for user creation events.
"""

import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import Member, MemberRole, Organisation, User

router = APIRouter()


class SignupRequest(BaseModel):
    """Request body for user signup."""
    email: str
    name: str | None = None
    clerk_user_id: str | None = None
    org_name: str | None = None


class SignupResponse(BaseModel):
    """Response after successful signup."""
    user_id: str
    email: str
    org_id: str
    org_slug: str


class LoginRequest(BaseModel):
    """Request body for login (Clerk user ID lookup)."""
    clerk_user_id: str


class UserResponse(BaseModel):
    """User info with their organisations."""
    user_id: str
    email: str
    name: str | None
    organisations: list[dict]


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:255]


@router.post("/signup", response_model=SignupResponse)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Create a new user, default org, and owner membership."""
    # Check if user already exists
    existing = await db.execute(
        select(User).where(User.email == body.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User with this email already exists")

    # Create user
    user = User(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        clerk_user_id=body.clerk_user_id,
    )
    db.add(user)

    # Create default organisation
    org_name = body.org_name or f"{body.name or body.email.split('@')[0]}'s Org"
    base_slug = _slugify(org_name)

    # Ensure slug is unique
    slug = base_slug
    counter = 1
    while True:
        slug_check = await db.execute(
            select(Organisation).where(Organisation.slug == slug)
        )
        if not slug_check.scalar_one_or_none():
            break
        slug = f"{base_slug}-{counter}"
        counter += 1

    org = Organisation(
        id=uuid.uuid4(),
        name=org_name,
        slug=slug,
    )
    db.add(org)

    # Create owner membership
    member = Member(
        id=uuid.uuid4(),
        organisation_id=org.id,
        user_id=user.id,
        role=MemberRole.OWNER,
    )
    db.add(member)

    await db.flush()

    return SignupResponse(
        user_id=str(user.id),
        email=user.email,
        org_id=str(org.id),
        org_slug=org.slug,
    )


@router.post("/login", response_model=UserResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Look up user by Clerk ID and return their organisations."""
    result = await db.execute(
        select(User).where(User.clerk_user_id == body.clerk_user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get all orgs user belongs to
    members_result = await db.execute(
        select(Member).where(Member.user_id == user.id)
    )
    members = members_result.scalars().all()

    organisations = []
    for m in members:
        org = await db.get(Organisation, m.organisation_id)
        if org:
            organisations.append({
                "org_id": str(org.id),
                "org_slug": org.slug,
                "org_name": org.name,
                "role": m.role.value,
                "plan": org.plan.value,
            })

    return UserResponse(
        user_id=str(user.id),
        email=user.email,
        name=user.name,
        organisations=organisations,
    )
