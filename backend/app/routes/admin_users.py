"""
Admin: User Management API
CRUD for platform users, role assignment, activation/deactivation.
All endpoints require admin role.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import AuditLog, User, UserRole
from app.security.auth import hash_password
from app.security.deps import get_current_user, require_admin

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
logger = logging.getLogger(__name__)


def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def _write_audit(actor: User, action: str, target_id: str, detail: dict) -> None:
    async with _sm()() as s:
        s.add(AuditLog(
            user_id=actor.id, username=actor.username,
            action=action, resource_type="user", resource_id=target_id,
            detail_json=json.dumps(detail, ensure_ascii=False)
        ))
        await s.commit()


def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": u.id,
        "username": u.username,
        "email": u.email,
        "role": u.role,
        "department_id": u.department_id,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
        "updated_at": u.updated_at.isoformat() if u.updated_at else None,
    }


# ── Schemas ───────────────────────────────────────────────────────────────────

VALID_ROLES = [r.value for r in UserRole]


class UserCreate(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = UserRole.EXECUTOR.value
    department_id: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    department_id: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None     # If set, resets password


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_users(
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    async with _sm()() as s:
        q = select(User)
        if role:
            q = q.where(User.role == role)
        if is_active is not None:
            q = q.where(User.is_active == is_active)
        q = q.order_by(User.created_at.desc()).limit(limit).offset(offset)
        rows = (await s.execute(q)).scalars().all()
        total = len(rows)
    return {"items": [_user_dict(u) for u in rows], "total": total}


@router.post("", status_code=201)
async def create_user(
    body: UserCreate,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role. Valid: {VALID_ROLES}")

    async with _sm()() as s:
        existing = (await s.execute(select(User).where(User.username == body.username))).scalars().first()
        if existing:
            raise HTTPException(status_code=409, detail="Username already taken")

        user = User(
            username=body.username,
            email=body.email,
            hashed_password=hash_password(body.password),
            role=body.role,
            department_id=body.department_id,
            is_active=True,
        )
        s.add(user)
        await s.commit()
        await s.refresh(user)

    await _write_audit(current_user, "create_user", user.id, {"username": user.username, "role": user.role})
    return _user_dict(user)


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    async with _sm()() as s:
        user = await s.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_dict(user)


@router.patch("/{user_id}")
async def update_user(
    user_id: str,
    body: UserUpdate,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    if body.role and body.role not in VALID_ROLES:
        raise HTTPException(status_code=422, detail=f"Invalid role. Valid: {VALID_ROLES}")

    async with _sm()() as s:
        user = await s.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        changes = {}
        if body.email is not None:
            user.email = body.email
            changes["email"] = body.email
        if body.role is not None:
            user.role = body.role
            changes["role"] = body.role
        if body.department_id is not None:
            user.department_id = body.department_id
            changes["department_id"] = body.department_id
        if body.is_active is not None:
            user.is_active = body.is_active
            changes["is_active"] = body.is_active
        if body.password:
            user.hashed_password = hash_password(body.password)
            changes["password_reset"] = True

        await s.commit()
        await s.refresh(user)

    await _write_audit(current_user, "update_user", user_id, changes)
    return _user_dict(user)


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Soft-delete: deactivate the user instead of destroying their data."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")

    async with _sm()() as s:
        user = await s.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.is_active = False
        await s.commit()

    await _write_audit(current_user, "deactivate_user", user_id, {"username": user.username})
    return {"ok": True, "user_id": user_id}


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    body: dict,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    new_password = body.get("password", "")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")

    async with _sm()() as s:
        user = await s.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.hashed_password = hash_password(new_password)
        await s.commit()

    await _write_audit(current_user, "reset_password", user_id, {"username": user.username})
    return {"ok": True}
