"""MySQL client for llm_proxy — device lookup, usage logging, and pricing."""
import json
import aiomysql
from typing import Optional, Any, Dict
from datetime import datetime

_pool: Optional[aiomysql.Pool] = None
_db_config: dict = {}


async def _get_pool() -> Optional[aiomysql.Pool]:
    global _pool
    if _pool is not None:
        return _pool
    if not _db_config:
        return None
    _pool = await aiomysql.create_pool(
        host=_db_config["host"],
        port=_db_config["port"],
        user=_db_config["user"],
        password=_db_config["password"],
        db=_db_config["database"],
        autocommit=True,
        charset="utf8mb4",
    )
    return _pool


def init_db(host: str, port: int, user: str, password: str, database: str) -> None:
    global _db_config, _pool
    _pool = None
    _db_config = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }
    if host and user:
        print(f"[llm_proxy] MySQL ready ({host}:{port}/{database})")
    else:
        print("[llm_proxy] MySQL not configured — device lookup will fail")


async def get_device(device_id: str) -> Optional[dict]:
    """Fetch a device row by device_id. Returns None if not found or unconfigured."""
    pool = await _get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM `devices` WHERE `device_id` = %s LIMIT 1",
                    (device_id,),
                )
                return await cur.fetchone()
    except Exception as e:
        print(f"[llm_proxy] get_device error: {e}")
        return None


async def get_device_binding(device_id: str) -> Optional[dict]:
    """
    Check device_bindings table for a device_id entry.
    Returns the first binding row (with user_id) if found, None otherwise.
    """
    pool = await _get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT * FROM `device_bindings` WHERE `device_id` = %s ORDER BY `created_at` ASC LIMIT 1",
                    (device_id,),
                )
                row = await cur.fetchone()
                print(f"[auth] device_bindings query result={row}")
                return row
    except Exception as e:
        print(f"[llm_proxy] get_device_binding error: {e}")
        return None


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
    pool = await _get_pool()
    if pool is None:
        return False

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ok = True

    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """INSERT INTO `llm_proxy_log`
                       (`user_id`, `device_id`, `timestamp`, `model`, `provider`,
                        `request_type`, `token_usage`, `cost_original`, `cost_currency`, `cost_cny`)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        user_id,
                        device_id,
                        now,
                        model,
                        provider,
                        request_type,
                        json.dumps(usage, ensure_ascii=False),
                        cost_original,
                        cost_currency,
                        cost_cny,
                    ),
                )
    except Exception as e:
        print(f"[llm_proxy] llm_proxy_log insert error: {e}")
        ok = False

    if user_id:
        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """INSERT INTO `llm_usage`
                           (`user_id`, `device_id`, `model`, `provider`, `request_type`,
                            `request_count`, `prompt_tokens`, `completion_tokens`, `total_tokens`,
                            `total_cost`, `first_used_at`, `last_used_at`)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON DUPLICATE KEY UPDATE
                               `request_count`     = `request_count`     + VALUES(`request_count`),
                               `prompt_tokens`     = `prompt_tokens`     + VALUES(`prompt_tokens`),
                               `completion_tokens` = `completion_tokens` + VALUES(`completion_tokens`),
                               `total_tokens`      = `total_tokens`      + VALUES(`total_tokens`),
                               `total_cost`        = `total_cost`        + VALUES(`total_cost`),
                               `last_used_at`      = VALUES(`last_used_at`)""",
                        (
                            user_id,
                            device_id,
                            model,
                            provider,
                            request_type,
                            1,
                            usage.get("prompt_tokens", 0),
                            usage.get("completion_tokens", 0),
                            usage.get("total_tokens", 0),
                            cost_cny,
                            now,
                            now,
                        ),
                    )
        except Exception as e:
            print(f"[llm_proxy] llm_usage upsert error: {e}")
            ok = False

    return ok


async def get_pricing(model: str, provider: str, request_type: str) -> Optional[dict]:
    """
    Fetch pricing for a (model, provider, request_type) triple from llm_pricing.
    Returns a dict with 'input_price' and 'output_price' (USD per 1M tokens), or None.
    """
    pool = await _get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """SELECT * FROM `llm_pricing`
                       WHERE `model` = %s AND `provider` = %s AND `request_type` = %s
                       LIMIT 1""",
                    (model, provider, request_type),
                )
                return await cur.fetchone()
    except Exception:
        return None
