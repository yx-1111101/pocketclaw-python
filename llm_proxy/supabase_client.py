"""Supabase client for llm_proxy — device lookup, usage logging, and pricing."""
import httpx
from typing import Optional, Any, Dict
from datetime import datetime

_url: str = ""
_headers: dict = {}


def init_supabase(url: str, key: str) -> None:
    global _url, _headers
    _url = url.rstrip("/") if url else ""
    _headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
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


async def log_proxy_request(
    user_id: Optional[str],
    device_id: str,
    model: str,
    provider: str,
    request_type: str,
    usage: Dict[str, Any],
    cost_original: float = 0.0,
    cost_currency: str = "USD",
    cost_cny: float = 0.0,
) -> bool:
    """
    Write one row to llm_proxy_log and upsert aggregated stats into llm_usage.
    Both writes are best-effort; failures are logged but do not raise.
    """
    if not _url:
        return False

    now = datetime.utcnow().isoformat()
    ok = True

    async with httpx.AsyncClient(timeout=5.0) as client:
        # 1. Raw request log
        log_entry = {
            "user_id": user_id,
            "device_id": device_id,
            "timestamp": now,
            "model": model,
            "provider": provider,
            "request_type": request_type,
            "usage": usage,
            "cost_original": cost_original,
            "cost_currency": cost_currency,
            "cost_cny": cost_cny,
        }
        try:
            resp = await client.post(
                f"{_url}/rest/v1/llm_proxy_log",
                headers=_headers,
                json=log_entry,
            )
            if resp.status_code >= 400:
                print(f"[llm_proxy] llm_proxy_log insert failed: {resp.text}")
                ok = False
        except Exception as e:
            print(f"[llm_proxy] llm_proxy_log insert error: {e}")
            ok = False

        # 2. Aggregated usage upsert (only when user_id is known)
        if user_id:
            upsert_headers = {**_headers, "Prefer": "resolution=merge-duplicates,return=minimal"}
            upsert_entry = {
                "user_id": user_id,
                "device_id": device_id,
                "model": model,
                "provider": provider,
                "request_type": request_type,
                "request_count": 1,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "total_cost": cost_cny,   # always accumulate in CNY
                "first_used_at": now,
                "last_used_at": now,
            }
            try:
                resp = await client.post(
                    f"{_url}/rest/v1/llm_usage",
                    headers=upsert_headers,
                    json=upsert_entry,
                )
                if resp.status_code >= 400:
                    print(f"[llm_proxy] llm_usage upsert failed: {resp.text}")
                    ok = False
            except Exception as e:
                print(f"[llm_proxy] llm_usage upsert error: {e}")
                ok = False

    return ok


async def get_pricing(model: str, provider: str, request_type: str) -> Optional[dict]:
    """
    Fetch pricing for a (model, provider, request_type) triple from llm_pricing.
    Returns a dict with 'input_price' and 'output_price' (USD per 1M tokens), or None.
    """
    if not _url:
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                f"{_url}/rest/v1/llm_pricing",
                headers=_headers,
                params={
                    "model": f"eq.{model}",
                    "provider": f"eq.{provider}",
                    "request_type": f"eq.{request_type}",
                },
            )
            if resp.status_code >= 400:
                return None
            rows = resp.json()
            return rows[0] if rows else None
    except Exception:
        return None
