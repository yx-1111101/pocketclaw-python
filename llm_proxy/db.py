"""轻量 Supabase 客户端 — llm_proxy 内部自用，不依赖 app/"""
import httpx
from typing import Any, Optional


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    async def get(self, table: str, filters: dict = None) -> Any:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.url}/rest/v1/{table}",
                headers=self.headers,
                params=filters or {},
            )
            if resp.status_code >= 400:
                return {"error": resp.text}
            return resp.json()


_db: Optional[SupabaseClient] = None


def init_db(url: str, key: str) -> None:
    global _db
    _db = SupabaseClient(url, key)


def get_db() -> SupabaseClient:
    return _db
