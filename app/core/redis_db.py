"""Redis 数据库客户端（替代 Supabase，用于设备配对存储）"""
import json
import uuid
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

# 全局 Redis 客户端
_redis: Optional[aioredis.Redis] = None


def init_redis(host: str = "localhost", port: int = 6379, db: int = 0):
    global _redis
    _redis = aioredis.Redis(host=host, port=port, db=db, decode_responses=True)
    print(f"[DB] 使用 Redis 数据库 ({host}:{port}/{db})")


def get_db() -> "RedisClient":
    return RedisClient(_redis)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------
# Each "table" is stored as a collection of Redis hashes:
#   <table>:row:<id>   → hash of all fields
#   <table>:index:<field>:<value> → set of row IDs that match (secondary index)
#
# Auto-incrementing integer IDs are simulated with a Redis INCR counter:
#   <table>:seq
# ---------------------------------------------------------------------------

def _row_key(table: str, row_id: str) -> str:
    return f"{table}:row:{row_id}"


def _index_key(table: str, field: str, value: str) -> str:
    return f"{table}:index:{field}:{value}"


def _seq_key(table: str) -> str:
    return f"{table}:seq"


# Fields that should be indexed for fast lookup (used by `get` with filters)
_INDEXED_FIELDS: Dict[str, List[str]] = {
    "devices": ["device_id"],
    "device_bindings": ["device_id", "user_id"],
    "users": ["openid", "user_id"],
}


class RedisClient:
    def __init__(self, r: aioredis.Redis):
        self._r = r

    # ------------------------------------------------------------------
    # get: return list of rows matching all filters
    # ------------------------------------------------------------------
    async def get(self, table: str, filters: dict = None) -> Any:
        if not filters:
            # Scan all rows for this table
            keys = []
            async for key in self._r.scan_iter(f"{table}:row:*"):
                keys.append(key)
            rows = []
            for key in keys:
                row = await self._r.hgetall(key)
                if row:
                    rows.append(_deserialize(row))
            return rows

        # Use the first indexed filter to narrow candidates
        indexed = _INDEXED_FIELDS.get(table, [])
        candidate_ids: Optional[set] = None

        for field, value in filters.items():
            if field in indexed:
                idx_key = _index_key(table, field, str(value))
                ids = await self._r.smembers(idx_key)
                if candidate_ids is None:
                    candidate_ids = set(ids)
                else:
                    candidate_ids &= set(ids)

        if candidate_ids is None:
            # No indexed field — full scan
            async for key in self._r.scan_iter(f"{table}:row:*"):
                row = await self._r.hgetall(key)
                if row:
                    candidate_ids = candidate_ids or set()
                    candidate_ids.add(key.split(":")[-1])

        if not candidate_ids:
            return []

        results = []
        for row_id in candidate_ids:
            row = await self._r.hgetall(_row_key(table, row_id))
            if not row:
                continue
            row = _deserialize(row)
            if all(str(row.get(k)) == str(v) for k, v in filters.items()):
                results.append(row)
        return results

    # ------------------------------------------------------------------
    # post: insert a new row, auto-assign integer `id`
    # ------------------------------------------------------------------
    async def post(self, table: str, data: dict) -> Any:
        row_id = str(await self._r.incr(_seq_key(table)))
        row = dict(data)
        row["id"] = row_id

        serialized = _serialize(row)
        await self._r.hset(_row_key(table, row_id), mapping=serialized)

        # Maintain secondary indexes
        for field in _INDEXED_FIELDS.get(table, []):
            if field in row:
                await self._r.sadd(_index_key(table, field, str(row[field])), row_id)

        return [row]

    # ------------------------------------------------------------------
    # patch: update fields on all rows matching filters
    # ------------------------------------------------------------------
    async def patch(self, table: str, filters: dict, data: dict) -> Any:
        rows = await self.get(table, filters)
        updated = []
        for row in rows:
            row_id = str(row["id"])

            # Remove old index entries for fields being overwritten
            for field in _INDEXED_FIELDS.get(table, []):
                if field in data and field in row:
                    await self._r.srem(_index_key(table, field, str(row[field])), row_id)

            row.update(data)
            await self._r.hset(_row_key(table, row_id), mapping=_serialize(row))

            # Re-add updated index entries
            for field in _INDEXED_FIELDS.get(table, []):
                if field in row:
                    await self._r.sadd(_index_key(table, field, str(row[field])), row_id)

            updated.append(row)
        return updated

    # ------------------------------------------------------------------
    # delete: remove all rows matching filters
    # ------------------------------------------------------------------
    async def delete(self, table: str, filters: dict) -> Any:
        rows = await self.get(table, filters)
        for row in rows:
            row_id = str(row["id"])
            # Clean up indexes
            for field in _INDEXED_FIELDS.get(table, []):
                if field in row:
                    await self._r.srem(_index_key(table, field, str(row[field])), row_id)
            await self._r.delete(_row_key(table, row_id))
        return {"success": True}


# ---------------------------------------------------------------------------
# Serialization helpers (Redis stores everything as strings)
# ---------------------------------------------------------------------------

def _serialize(row: dict) -> dict:
    """Convert a row dict to string-only values for Redis HSET."""
    result = {}
    for k, v in row.items():
        if v is None:
            result[k] = ""
        elif isinstance(v, (dict, list)):
            result[k] = json.dumps(v)
        else:
            result[k] = str(v)
    return result


def _deserialize(row: dict) -> dict:
    """Convert a Redis HGETALL result back to Python types."""
    result = {}
    for k, v in row.items():
        if v == "":
            result[k] = None
        else:
            # Try JSON decode for nested structures
            try:
                parsed = json.loads(v)
                if isinstance(parsed, (dict, list)):
                    result[k] = parsed
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
            # Try int
            try:
                result[k] = int(v)
                continue
            except ValueError:
                pass
            result[k] = v
    return result
