"""Supabase 客户端"""
import httpx
from typing import Optional, Any


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
        """查询数据"""
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
        """插入数据"""
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
        """更新数据"""
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
        """删除数据"""
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
db: Optional[SupabaseClient] = None


def init_db(url: str, key: str):
    """初始化数据库客户端"""
    global db
    db = SupabaseClient(url, key)


def get_db() -> SupabaseClient:
    """获取数据库客户端"""
    return db
