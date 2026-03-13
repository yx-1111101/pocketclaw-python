"""Supabase client for llm_proxy — device lookup only."""
import httpx
from typing import Optional

_url: str = ""
_headers: dict = {}


def init_supabase(url: str, key: str) -> None:
    global _url, _headers
    _url = url.rstrip("/") if url else ""
    _headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if url and key:
        print(f"[llm_proxy] Supabase ready ({url[:40]}...)")
    else:
        print("[llm_proxy] Supabase not configured — device lookup will fail")


async def get_device(device_id: str) -> Optional[dict]:
    """Fetch a device row by device_id. Returns None if not found or unconfigured."""
    if not _url:
        return None
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{_url}/rest/v1/devices",
            headers=_headers,
            params={"device_id": f"eq.{device_id}"},
        )
        if resp.status_code >= 400:
            return None
        rows = resp.json()
        return rows[0] if rows else None
