"""Redis 缓存客户端（app/core 层，供 main.py 初始化使用）"""
import redis.asyncio as aioredis
from typing import Optional

_redis: Optional[aioredis.Redis] = None


def init_cache(host: str = "localhost", port: int = 6379, db: int = 0) -> None:
    global _redis
    _redis = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)
    print(f"[Cache] Redis 连接已初始化 ({host}:{port}/{db})")


def get_cache() -> Optional[aioredis.Redis]:
    return _redis
