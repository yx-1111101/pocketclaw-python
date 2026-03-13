"""Redis 缓存客户端（短生命周期数据：device_secret、配对码等）"""
import redis.asyncio as aioredis
from typing import Optional

_redis: Optional[aioredis.Redis] = None


def init_cache(host: str = "localhost", port: int = 6379, db: int = 0) -> None:
    global _redis
    _redis = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)
    print(f"[Cache] Redis 缓存已就绪 ({host}:{port}/{db})")


async def cache_set(key: str, value: str, ttl_seconds: int = None) -> None:
    if _redis is None:
        return
    if ttl_seconds:
        await _redis.set(key, value, ex=ttl_seconds)
    else:
        await _redis.set(key, value)


async def cache_get(key: str) -> Optional[str]:
    if _redis is None:
        return None
    return await _redis.get(key)


async def cache_delete(key: str) -> None:
    if _redis is None:
        return
    await _redis.delete(key)
