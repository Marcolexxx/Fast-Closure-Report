from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import redis.asyncio as redis_async

from app.config import get_settings


@lru_cache(maxsize=1)
def get_redis_client() -> redis_async.Redis:
    settings = get_settings()
    url = settings.redis_url or os.environ.get("REDIS_URL", "redis://redis:6379/0")
    return redis_async.from_url(url, decode_responses=True)


async def acquire_lock(key: str, value: str, ttl_s: int = 60) -> bool:
    client = get_redis_client()
    # SET key value NX EX ttl_s
    result = await client.set(name=key, value=value, nx=True, ex=ttl_s)
    return bool(result)


async def release_lock(key: str, value: str) -> bool:
    client = get_redis_client()
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    result = await client.eval(lua_script, 1, key, value)
    return bool(result)

