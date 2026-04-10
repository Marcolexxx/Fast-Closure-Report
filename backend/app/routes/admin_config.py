"""
Admin: System Configuration API
Manages LLM settings, external API keys, AI thresholds, and agent parameters.
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
from app.models import AuditLog, SystemConfig, User
from app.security.deps import get_current_user, require_admin

router = APIRouter(prefix="/admin/config", tags=["admin-config"])
logger = logging.getLogger(__name__)


def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def _write_audit(user: User, action: str, resource_type: str, resource_id: str, detail: dict) -> None:
    async with _sm()() as s:
        s.add(AuditLog(
            user_id=user.id, username=user.username,
            action=action, resource_type=resource_type, resource_id=resource_id,
            detail_json=json.dumps(detail, ensure_ascii=False)
        ))
        await s.commit()


def _mask(cfg: SystemConfig) -> dict:
    value = cfg.config_value
    if cfg.is_secret and value:
        # Show only last 4 chars
        value = "****" + value[-4:] if len(value) > 4 else "****"
    return {
        "id": cfg.id,
        "namespace": cfg.namespace,
        "config_key": cfg.config_key,
        "config_value": value,
        "description": cfg.description,
        "is_secret": cfg.is_secret,
        "updated_at": cfg.updated_at.isoformat() if cfg.updated_at else None,
    }


# ── Schemas ──────────────────────────────────────────────────────────────────

class ConfigUpsert(BaseModel):
    namespace: str      # llm | api_keys | thresholds | agent
    config_key: str
    config_value: str
    description: Optional[str] = None
    is_secret: bool = False


class BulkConfigUpsert(BaseModel):
    items: list[ConfigUpsert]


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_configs(
    namespace: Optional[str] = None,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """List all system configs, optionally filtered by namespace."""
    async with _sm()() as s:
        q = select(SystemConfig)
        if namespace:
            q = q.where(SystemConfig.namespace == namespace)
        rows = (await s.execute(q.order_by(SystemConfig.namespace, SystemConfig.config_key))).scalars().all()
    return {"items": [_mask(r) for r in rows]}


@router.put("")
async def upsert_config(
    body: ConfigUpsert,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Create or update a single config entry."""
    async with _sm()() as s:
        row = (await s.execute(
            select(SystemConfig).where(
                SystemConfig.namespace == body.namespace,
                SystemConfig.config_key == body.config_key
            )
        )).scalars().first()
        if row:
            row.config_value = body.config_value
            row.description = body.description
            row.is_secret = body.is_secret
            row.updated_by = current_user.id
        else:
            row = SystemConfig(
                namespace=body.namespace,
                config_key=body.config_key,
                config_value=body.config_value,
                description=body.description,
                is_secret=body.is_secret,
                updated_by=current_user.id,
            )
            s.add(row)
        await s.commit()
        await s.refresh(row)

    await _write_audit(current_user, "update_config", "config", f"{body.namespace}/{body.config_key}", {
        "namespace": body.namespace, "key": body.config_key, "is_secret": body.is_secret
    })
    return _mask(row)


@router.put("/bulk")
async def bulk_upsert_configs(
    body: BulkConfigUpsert,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Batch update multiple config entries (e.g., save LLM settings form)."""
    async with _sm()() as s:
        results = []
        for item in body.items:
            row = (await s.execute(
                select(SystemConfig).where(
                    SystemConfig.namespace == item.namespace,
                    SystemConfig.config_key == item.config_key
                )
            )).scalars().first()
            if row:
                row.config_value = item.config_value
                row.description = item.description
                row.is_secret = item.is_secret
                row.updated_by = current_user.id
            else:
                row = SystemConfig(
                    namespace=item.namespace, config_key=item.config_key,
                    config_value=item.config_value, description=item.description,
                    is_secret=item.is_secret, updated_by=current_user.id,
                )
                s.add(row)
            results.append(row)
        await s.commit()

    await _write_audit(current_user, "bulk_update_config", "config", "bulk", {"count": len(body.items)})
    return {"updated": len(results)}


@router.delete("/{namespace}/{config_key}")
async def delete_config(
    namespace: str,
    config_key: str,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    async with _sm()() as s:
        row = (await s.execute(
            select(SystemConfig).where(
                SystemConfig.namespace == namespace,
                SystemConfig.config_key == config_key
            )
        )).scalars().first()
        if not row:
            raise HTTPException(status_code=404, detail="Config not found")
        await s.delete(row)
        await s.commit()
    return {"ok": True}


@router.get("/audit-log")
async def get_audit_log(
    limit: int = 50,
    current_user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Return recent admin audit log entries."""
    async with _sm()() as s:
        rows = (await s.execute(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        )).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "username": r.username,
                "action": r.action,
                "resource_type": r.resource_type,
                "resource_id": r.resource_id,
                "detail_json": r.detail_json,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }
