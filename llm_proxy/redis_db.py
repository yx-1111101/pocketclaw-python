"""Redis cache for llm_proxy — device row cache only."""
import json
from typing import Optional

import redis.asyncio as aioredis

_redis: Optional[aioredis.Redis] = None

DEVICE_CACHE_TTL = 60  # seconds


def init_cache(host: str = "localhost", port: int = 6379, db: int = 0) -> None:
    global _redis
    _redis = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)
    print(f"[llm_proxy] Redis cache ready ({host}:{port}/{db})")


async def get_device(device_id: str) -> Optional[dict]:
    if _redis is None:
        return None
    raw = await _redis.get(f"llm_proxy:device:{device_id}")
    if raw is None:
        return None
    return json.loads(raw)


async def set_device(device_id: str, device: dict) -> None:
    if _redis is None:
        return
    await _redis.set(f"llm_proxy:device:{device_id}", json.dumps(device), ex=DEVICE_CACHE_TTL)


async def invalidate_device(device_id: str) -> None:
    if _redis is None:
        return
    await _redis.delete(f"llm_proxy:device:{device_id}")
