"""OpenClaw 系统配置 API"""
import json
import os
import signal
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any

router = APIRouter(prefix="/system", tags=["系统配置"])

CONFIG_PATH = Path(os.path.expanduser("~/.openclaw/openclaw.json"))

SENSITIVE_KEYS = {"token", "password", "apikey", "secret", "bottoken", "appid", "appsecret"}


def _is_sensitive(key: str) -> bool:
    return key.lower().replace("_", "").replace("-", "") in SENSITIVE_KEYS


def _mask(obj, depth=0):
    """屏蔽敏感字段，用于展示"""
    if depth > 5:
        return "..."
    if isinstance(obj, dict):
        return {k: "***" if _is_sensitive(k) else _mask(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_mask(i, depth + 1) for i in obj]
    return obj


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置失败: {e}")


def _write_config(config: dict):
    try:
        CONFIG_PATH.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置失败: {e}")


def _deep_merge(base: dict, patch: dict) -> dict:
    """深度合并，patch 覆盖 base"""
    result = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _reload_gateway():
    """发送 SIGUSR1 让 Gateway 热重载配置"""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "openclaw"],
            capture_output=True, text=True
        )
        pids = [int(p) for p in result.stdout.strip().split() if p.isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGUSR1)
            except ProcessLookupError:
                pass
        return bool(pids)
    except Exception:
        return False


# ── 频道配置 ──────────────────────────────────────────────

SUPPORTED_CHANNELS = ["telegram", "discord", "slack", "whatsapp", "signal", "feishu", "wecom"]

@router.get("/config/channels")
async def get_channels():
    """获取所有频道配置（敏感字段已屏蔽）"""
    config = _read_config()
    channels = config.get("channels", {})

    result = []
    for name in SUPPORTED_CHANNELS:
        ch = channels.get(name, {})
        result.append({
            "name": name,
            "enabled": ch.get("enabled", False),
            "config": _mask(ch),
        })
    return {"success": True, "channels": result}


class ChannelPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    bot_token: Optional[str] = None     # Telegram/Discord
    account_id: Optional[str] = "default"
    extra: Optional[dict] = None         # 其他任意配置


@router.patch("/config/channels/{channel}")
async def patch_channel(channel: str, body: ChannelPatchRequest):
    """更新某个频道配置"""
    if channel not in SUPPORTED_CHANNELS:
        raise HTTPException(status_code=400, detail=f"不支持的频道: {channel}")

    config = _read_config()
    channels = config.setdefault("channels", {})
    ch = channels.setdefault(channel, {})

    if body.enabled is not None:
        ch["enabled"] = body.enabled

    # bot token 存到 accounts.<account_id>.botToken
    if body.bot_token:
        account_id = body.account_id or "default"
        accounts = ch.setdefault("accounts", {})
        acc = accounts.setdefault(account_id, {})
        acc["botToken"] = body.bot_token

    if body.extra:
        ch = _deep_merge(ch, body.extra)

    channels[channel] = ch
    _write_config(config)
    _reload_gateway()

    return {"success": True, "message": f"{channel} 配置已更新，Gateway 正在重载"}


# ── 模型 API Key ──────────────────────────────────────────

SUPPORTED_PROVIDERS = ["anthropic", "openai", "google", "minimax", "openrouter", "groq", "deepseek"]


@router.get("/config/models")
async def get_models():
    """获取所有模型 provider 的配置（API key 已屏蔽）"""
    config = _read_config()
    auth_profiles = config.get("auth", {}).get("profiles", {})

    result = []
    for provider in SUPPORTED_PROVIDERS:
        # 找到该 provider 的所有 profile
        profiles = {k: v for k, v in auth_profiles.items() if k.startswith(f"{provider}:")}
        has_key = any(
            v.get("mode") == "apiKey" or v.get("apiKey")
            for v in profiles.values()
        )
        result.append({
            "provider": provider,
            "has_key": has_key,
            "profile_count": len(profiles),
        })

    return {"success": True, "models": result}


class ModelKeyRequest(BaseModel):
    api_key: str
    profile: Optional[str] = "default"   # e.g. "default", "pro"


@router.post("/config/models/{provider}/apikey")
async def set_model_apikey(provider: str, body: ModelKeyRequest):
    """设置模型 provider 的 API Key"""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"不支持的 provider: {provider}")
    if not body.api_key or len(body.api_key) < 10:
        raise HTTPException(status_code=400, detail="API Key 不合法")

    config = _read_config()
    auth = config.setdefault("auth", {})
    profiles = auth.setdefault("profiles", {})

    profile_key = f"{provider}:{body.profile or 'default'}"
    profile = profiles.setdefault(profile_key, {"provider": provider})
    profile["mode"] = "apiKey"
    profile["apiKey"] = body.api_key

    _write_config(config)
    _reload_gateway()

    return {"success": True, "message": f"{provider} API Key 已更新，Gateway 正在重载"}


@router.delete("/config/models/{provider}/apikey")
async def delete_model_apikey(provider: str, profile: str = "default"):
    """删除模型 provider 的 API Key"""
    config = _read_config()
    profiles = config.get("auth", {}).get("profiles", {})
    profile_key = f"{provider}:{profile}"

    if profile_key in profiles:
        del profiles[profile_key]
        _write_config(config)
        _reload_gateway()

    return {"success": True}


# ── Gateway 状态 ──────────────────────────────────────────

@router.get("/gateway/status")
async def gateway_status():
    """检查 Gateway 是否在线"""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get("http://127.0.0.1:18789/health")
            return {"success": True, "online": True, "data": resp.json()}
    except Exception:
        return {"success": True, "online": False}


@router.post("/gateway/reload")
async def gateway_reload():
    """手动触发 Gateway 热重载"""
    ok = _reload_gateway()
    return {"success": True, "reloaded": ok}
