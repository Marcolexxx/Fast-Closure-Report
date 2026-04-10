"""
Admin: PPT Template Management
Upload, list, activate, set-default PPT templates.
All endpoints require admin role.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db import get_engine
from app.models import AuditLog, PPTTemplate, User
from app.security.deps import get_current_user, require_admin

router = APIRouter(prefix="/admin/templates", tags=["admin-templates"])
logger = logging.getLogger(__name__)


def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


def _tpl_dict(t: PPTTemplate) -> dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "file_path": t.file_path,
        "is_default": t.is_default,
        "is_active": t.is_active,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
async def list_templates(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """List all PPT templates. Any logged-in user can view."""
    async with _sm()() as s:
        rows = (await s.execute(
            select(PPTTemplate).where(PPTTemplate.is_active == True).order_by(PPTTemplate.created_at.desc())
        )).scalars().all()
    return {"items": [_tpl_dict(t) for t in rows]}


@router.post("", status_code=201)
async def upload_template(
    name: str,
    file: UploadFile = File(...),
    description: Optional[str] = None,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Upload a new .pptx template file."""
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(status_code=415, detail="Only .pptx files are supported")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    settings = get_settings()
    sha256 = hashlib.sha256(content).hexdigest()
    dest_dir = os.path.join(settings.file_storage_root, "templates")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, f"{sha256[:8]}_{file.filename}")

    if not os.path.exists(dest_path):
        with open(dest_path, "wb") as fp:
            fp.write(content)

    async with _sm()() as s:
        tpl = PPTTemplate(
            name=name,
            description=description,
            file_path=dest_path,
            is_default=False,
            is_active=True,
            created_by=current_user.id,
        )
        s.add(tpl)
        await s.commit()
        await s.refresh(tpl)

    logger.info(f"admin_template_uploaded: {tpl.id} by {current_user.username}")
    return _tpl_dict(tpl)


@router.patch("/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdate,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    async with _sm()() as s:
        tpl = await s.get(PPTTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        if body.name is not None:
            tpl.name = body.name
        if body.description is not None:
            tpl.description = body.description
        if body.is_active is not None:
            tpl.is_active = body.is_active
        await s.commit()
        await s.refresh(tpl)
    return _tpl_dict(tpl)


@router.post("/{template_id}/set-default")
async def set_default_template(
    template_id: str,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Set a template as the system default."""
    async with _sm()() as s:
        tpl = await s.get(PPTTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        if not tpl.is_active:
            raise HTTPException(status_code=400, detail="Cannot set a deleted template as default")

        # Unset all existing defaults
        existing_defaults = (await s.execute(
            select(PPTTemplate).where(PPTTemplate.is_default == True)
        )).scalars().all()
        for t in existing_defaults:
            t.is_default = False

        tpl.is_default = True
        await s.commit()
        await s.refresh(tpl)
    return _tpl_dict(tpl)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    async with _sm()() as s:
        tpl = await s.get(PPTTemplate, template_id)
        if not tpl:
            raise HTTPException(status_code=404, detail="Template not found")
        tpl.is_active = False  # Soft delete
        await s.commit()
    return {"ok": True}
