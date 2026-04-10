from __future__ import annotations

import time
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import get_engine
from app.models import SystemConfig


def _sm() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


_CACHE: dict[str, tuple[float, dict[str, str]]] = {}
_TTL_S = 5.0


async def get_namespace_map(namespace: str) -> dict[str, str]:
    """
    Read SystemConfig by namespace as a key->value map.
    Cached with a short TTL to avoid hammering DB on each LLM call.
    """
    now = time.time()
    cached = _CACHE.get(namespace)
    if cached and now - cached[0] < _TTL_S:
        return cached[1]

    async with _sm()() as s:
        rows = (
            await s.execute(select(SystemConfig).where(SystemConfig.namespace == namespace))
        ).scalars().all()
    m = {r.config_key: (r.config_value or "") for r in rows}
    _CACHE[namespace] = (now, m)
    return m


async def get_config_value(namespace: str, key: str, default: Optional[str] = None) -> Optional[str]:
    m = await get_namespace_map(namespace)
    if key in m:
        return m[key]
    return default

