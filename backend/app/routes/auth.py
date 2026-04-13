from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import jwt
from fastapi import APIRouter, HTTPException, status, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine, get_session_maker
from app.models import User, UserRole
from app.security.auth import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.security.deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

# Use the global session maker
_session_maker = get_session_maker


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    role: str = UserRole.EXECUTOR.value
    department_id: str | None = None


class RefreshRequest(BaseModel):
    pass # Empty as we will use cookie


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict[str, Any]:
    async with _session_maker()() as session:
        result = await session.execute(select(User).where(User.username == body.username))
        user = result.scalars().first()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account inactive")

    access_token = create_access_token(user.id, user.role, user.username, user.department_id)
    refresh_token = create_refresh_token(user.id)
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True, max_age=30*24*3600, samesite="lax", path="/"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "department_id": user.department_id,
        },
    }


@router.post("/register")
async def register(body: RegisterRequest, response: Response) -> dict[str, Any]:
    if body.role == UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="Cannot self-register as admin")

    async with _session_maker()() as session:
        existing = (await session.execute(select(User).where(User.username == body.username))).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

        user = User(
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
            role=body.role if body.role in [r.value for r in UserRole] else UserRole.EXECUTOR.value,
            department_id=body.department_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    access_token = create_access_token(user.id, user.role, user.username, user.department_id)
    refresh_token = create_refresh_token(user.id)
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True, max_age=30*24*3600, samesite="lax", path="/"
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }


@router.post("/refresh")
async def refresh(request: Request, response: Response) -> dict[str, Any]:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token missing")

    try:
        payload = decode_token(refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Wrong token type")

    user_id: str = payload["sub"]
    async with _session_maker()() as session:
        user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    access_token = create_access_token(user.id, user.role, user.username, user.department_id)
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(key="refresh_token", path="/")
    return {"status": "ok"}

@router.get("/me")
async def me(current_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role": current_user.role,
        "department_id": current_user.department_id,
        "is_active": current_user.is_active,
    }
