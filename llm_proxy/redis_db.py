"""轻量 Redis 客户端 — llm_proxy 内部自用，不依赖 app/"""
import json
from typing import Any, Optional

import redis.asyncio as aioredis


class RedisClient:
    def __init__(self, host: str, port: int, db: int):
        self._r = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)

    async def get(self, table: str, filters: dict = None):
        if not filters:
            keys = []
            async for key in self._r.scan_iter(f"{table}:row:*"):
                keys.append(key)
            rows = []
            for key in keys:
                row = await self._r.hgetall(key)
                if row:
                    rows.append(_deserialize(row))
            return rows

        results = []
        for field, value in filters.items():
            idx_key = f"{table}:index:{field}:{value}"
            row_ids = await self._r.smembers(idx_key)
            for row_id in row_ids:
                row = await self._r.hgetall(f"{table}:row:{row_id}")
                if row:
                    d = _deserialize(row)
                    if all(str(d.get(k)) == str(v) for k, v in filters.items()):
                        results.append(d)
        return results


def _deserialize(row: dict) -> dict:
    result = {}
    for k, v in row.items():
        if v == "":
            result[k] = None
        else:
            try:
                parsed = json.loads(v)
                if isinstance(parsed, (dict, list)):
                    result[k] = parsed
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                result[k] = int(v)
                continue
            except ValueError:
                pass
            result[k] = v
    return result


_db = None


def init_db(host: str, port: int, db: int) -> None:
    global _db
    _db = RedisClient(host, port, db)


def get_db():
    return _db
