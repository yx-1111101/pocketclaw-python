"""Supabase 客户端（含本地内存 fallback，无需 Supabase 也可本地联调）"""
import httpx
from typing import Optional, Any, List, Dict


class MemoryClient:
    """
    本地内存数据库（用于无 Supabase 配置时的联调）。
    数据在进程重启后清空，仅供开发测试使用。
    """

    def __init__(self):
        self._tables: Dict[str, List[dict]] = {}

    def _table(self, name: str) -> List[dict]:
        return self._tables.setdefault(name, [])

    async def get(self, table: str, filters: dict = None) -> Any:
        rows = self._table(table)
        if not filters:
            return list(rows)
        result = []
        for row in rows:
            if all(row.get(k) == v for k, v in filters.items()):
                result.append(row)
        return result

    async def post(self, table: str, data: dict) -> Any:
        self._table(table).append(dict(data))
        return [dict(data)]

    async def patch(self, table: str, filters: dict, data: dict) -> Any:
        updated = []
        for row in self._table(table):
            if all(row.get(k) == v for k, v in filters.items()):
                row.update(data)
                updated.append(dict(row))
        return updated

    async def delete(self, table: str, filters: dict) -> Any:
        rows = self._table(table)
        self._tables[table] = [
            r for r in rows
            if not all(r.get(k) == v for k, v in filters.items())
        ]
        return {"success": True}


class SupabaseClient:
    """Supabase REST API 客户端"""

    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def get(self, table: str, filters: dict = None) -> Any:
        async with httpx.AsyncClient() as client:
            params = filters or {}
            resp = await client.get(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                params=params
            )
            if resp.status_code >= 400:
                return {"error": resp.text}
            return resp.json()

    async def post(self, table: str, data: dict) -> Any:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                json=data
            )
            if resp.status_code >= 400:
                return {"error": resp.text}
            return resp.json()

    async def patch(self, table: str, filters: dict, data: dict) -> Any:
        async with httpx.AsyncClient() as client:
            filter_str = ",".join([f"{k}=eq.{v}" for k, v in filters.items()])
            resp = await client.patch(
                f"{self.url}/rest/v1/{table}?{filter_str}",
                headers=self.headers,
                json=data
            )
            if resp.status_code >= 400:
                return {"error": resp.text}
            return resp.json()

    async def delete(self, table: str, filters: dict) -> Any:
        async with httpx.AsyncClient() as client:
            filter_str = ",".join([f"{k}=eq.{v}" for k, v in filters.items()])
            resp = await client.delete(
                f"{self.url}/rest/v1/{table}?{filter_str}",
                headers=self.headers
            )
            if resp.status_code >= 400:
                return {"error": resp.text}
            return {"success": True}


# 全局数据库客户端
db: Optional[Any] = None


def init_db(url: str, key: str):
    """初始化数据库客户端；URL 或 Key 为空时自动使用内存模式"""
    global db
    if url and key:
        db = SupabaseClient(url, key)
        print("[DB] 使用 Supabase 云数据库")
    else:
        db = MemoryClient()
        print("[DB] Supabase 未配置，使用内存数据库（仅限本地联调）")


def get_db() -> Any:
    """获取数据库客户端"""
    return db
