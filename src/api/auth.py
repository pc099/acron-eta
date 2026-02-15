import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import get_async_session
from src.db.models import ApiKeyModel, OrgModel, UserModel

auth_router = APIRouter(prefix="/auth", tags=["Auth"])


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    org_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    api_key: str
    user_id: int
    org_id: int
    email: str


def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(pwd_bytes, hashed_bytes)


@auth_router.post("/signup", response_model=AuthResponse)
async def signup(
    user_data: UserCreate, session: AsyncSession = Depends(get_async_session)
):
    # Check if user exists
    stmt = select(UserModel).where(UserModel.email == user_data.email)
    result = await session.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    # Create Org
    org = OrgModel(name=user_data.org_name or f"{user_data.email}'s Org")
    session.add(org)
    await session.flush()  # to get org.id

    # Create User
    user = UserModel(
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        org_id=org.id,
    )
    session.add(user)
    await session.flush() # to get user.id

    # Generate API key (bcrypt hash so AuthMiddleware.validate_api_key can verify it)
    raw_key = f"acron_{secrets.token_urlsafe(32)}"
    key_hash = bcrypt.hashpw(
        raw_key.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    api_key = ApiKeyModel(
        key_prefix=raw_key[:12],
        key_hash=key_hash,
        user_id=str(user.id), # ApiKeyModel uses string user_id
        org_id=str(org.id),
        scopes=["admin"], # Default scope
        expires_at=datetime.utcnow() + timedelta(days=365),
    )
    session.add(api_key)
    await session.commit()

    return AuthResponse(
        api_key=raw_key,
        user_id=user.id,
        org_id=org.id,
        email=user.email,
    )


@auth_router.post("/login", response_model=AuthResponse)
async def login(
    user_data: UserLogin, session: AsyncSession = Depends(get_async_session)
):
    # Find User
    stmt = select(UserModel).where(UserModel.email == user_data.email)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Generate a short-lived API key (bcrypt hash so AuthMiddleware can verify it)
    raw_key = f"acron_sess_{secrets.token_urlsafe(32)}"
    key_hash = bcrypt.hashpw(
        raw_key.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    api_key_entry = ApiKeyModel(
        key_prefix=raw_key[:12],
        key_hash=key_hash,
        user_id=str(user.id),
        org_id=str(user.org_id) if user.org_id else "unknown",
        scopes=["admin", "dashboard"],
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    session.add(api_key_entry)
    await session.commit()

    return AuthResponse(
        api_key=raw_key,
        user_id=user.id,
        org_id=user.org_id or 0,
        email=user.email,
    )

