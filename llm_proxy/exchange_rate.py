"""Exchange rate fetching with fallback chain.

Tries two public APIs in order; falls back to a hardcoded default if both fail.
Results are cached in-process for CACHE_TTL seconds to avoid hammering the APIs.
"""
import time
from typing import Optional

import httpx

_FALLBACK_USD_TO_CNY = 7.5
_CACHE_TTL = 3600  # 1 hour

_cached_rate: Optional[float] = None
_cached_at: float = 0.0

_APIS = [
    "https://api.exchangeratesapi.io/latest?base=USD&symbols=CNY",
    "https://api.exchangerate-api.com/v4/latest/USD",
]


async def _fetch_from(url: str, client: httpx.AsyncClient) -> Optional[float]:
    try:
        resp = await client.get(url, timeout=5.0)
        if resp.status_code >= 400:
            return None
        data = resp.json()
        rate = data.get("rates", {}).get("CNY")
        return float(rate) if rate is not None else None
    except Exception:
        return None


async def get_usd_to_cny() -> float:
    """Return the current USD → CNY exchange rate.

    Resolution order:
      1. In-process cache (TTL: 1 hour)
      2. exchangeratesapi.io
      3. exchangerate-api.com
      4. Hardcoded fallback (7.5)
    """
    global _cached_rate, _cached_at

    if _cached_rate is not None and (time.monotonic() - _cached_at) < _CACHE_TTL:
        return _cached_rate

    async with httpx.AsyncClient() as client:
        for url in _APIS:
            rate = await _fetch_from(url, client)
            if rate is not None:
                _cached_rate = rate
                _cached_at = time.monotonic()
                return rate

    print(f"[llm_proxy] Exchange rate fetch failed — using fallback {_FALLBACK_USD_TO_CNY}")
    return _FALLBACK_USD_TO_CNY


def convert_to_cny(amount: float, currency: str, usd_to_cny: float) -> float:
    """Convert an amount in the given currency to CNY."""
    currency = currency.upper()
    if currency == "CNY":
        return amount
    if currency == "USD":
        return amount * usd_to_cny
    # Unknown currency — treat as USD as a safe default
    print(f"[llm_proxy] Unknown currency '{currency}', treating as USD for CNY conversion")
    return amount * usd_to_cny
