"""
Channel management API - 通过 Gateway RPC 管理 OpenClaw 渠道

渠道配置通过 config.get + config.patch 写入 ~/.openclaw/openclaw.json，
渠道状态通过 channels.status 从 Gateway 实时读取，
断开渠道通过 channels.logout RPC。
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
import json
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.db import get_db

router = APIRouter(prefix="/channels", tags=["channels"])
device_router = APIRouter(prefix="/devices", tags=["设备-频道"])
logger = logging.getLogger(__name__)


# ── 渠道定义 ─────────────────────────────────────────────────
# native=True  → OpenClaw 内置渠道，通过 config.patch 配置
# native=False → 插件渠道，仅做 UI 占位
# coming_soon=True → 暂不支持配置

CHANNEL_TYPES: dict[str, dict] = {
    "telegram": {
        "name": "Telegram",
        "icon": "telegram",
        "color": "#229ED9",
        "desc": "通过 Telegram Bot API 接入",
        "native": True,
        "config_fields": [
            {"key": "botToken", "label": "Bot Token", "type": "secret",
             "placeholder": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"},
        ],
        "config_key_map": {"botToken": "botToken"},
    },
    "discord": {
        "name": "Discord",
        "icon": "discord",
        "color": "#5865F2",
        "desc": "通过 Discord Bot 接入",
        "native": True,
        "config_fields": [
            {"key": "token", "label": "Bot Token", "type": "secret",
             "placeholder": "请输入 Discord Bot Token"},
        ],
        "config_key_map": {"token": "token"},
    },
    "slack": {
        "name": "Slack",
        "icon": "slack",
        "color": "#4A154B",
        "desc": "通过 Slack Socket Mode 接入",
        "native": True,
        "config_fields": [
            {"key": "appToken", "label": "App Token", "type": "secret",
             "placeholder": "xapp-..."},
            {"key": "botToken", "label": "Bot Token", "type": "secret",
             "placeholder": "xoxb-..."},
        ],
        "config_key_map": {"appToken": "appToken", "botToken": "botToken"},
    },
    "whatsapp": {
        "name": "WhatsApp",
        "icon": "whatsapp",
        "color": "#25D366",
        "desc": "需要二维码配对（即将支持）",
        "native": True,
        "coming_soon": True,
        "config_fields": [],
        "config_key_map": {},
    },
    "signal": {
        "name": "Signal",
        "icon": "signal",
        "color": "#3A76F0",
        "desc": "需要 signal-cli 环境（即将支持）",
        "native": True,
        "coming_soon": True,
        "config_fields": [],
        "config_key_map": {},
    },
    "feishu": {
        "name": "飞书",
        "icon": "feishu",
        "color": "#4A90E2",
        "desc": "需安装飞书插件",
        "native": False,
        "config_fields": [
            {"key": "appId", "label": "App ID", "type": "text", "placeholder": "请输入 App ID"},
            {"key": "appSecret", "label": "App Secret", "type": "secret", "placeholder": "请输入 App Secret"},
        ],
    },
    "dingtalk": {
        "name": "钉钉",
        "icon": "dingtalk",
        "color": "#FF6A00",
        "desc": "需安装钉钉插件",
        "native": False,
        "config_fields": [
            {"key": "appKey", "label": "App Key", "type": "text", "placeholder": "请输入 App Key"},
            {"key": "appSecret", "label": "App Secret", "type": "secret", "placeholder": "请输入 App Secret"},
        ],
    },
    "wecom": {
        "name": "企业微信",
        "icon": "wecom",
        "color": "#07C160",
        "desc": "需安装企业微信插件",
        "native": False,
        "config_fields": [
            {"key": "corpId", "label": "企业ID", "type": "text", "placeholder": "请输入企业ID"},
            {"key": "agentId", "label": "AgentId", "type": "text", "placeholder": "请输入 AgentId"},
            {"key": "secret", "label": "Secret", "type": "secret", "placeholder": "请输入 Secret"},
        ],
    },
    "qq": {
        "name": "QQ",
        "icon": "qq",
        "color": "#12B7F5",
        "desc": "需安装 QQ 机器人插件",
        "native": False,
        "config_fields": [
            {"key": "appId", "label": "AppID", "type": "text", "placeholder": "请输入 AppID"},
            {"key": "token", "label": "Token", "type": "secret", "placeholder": "请输入 Token"},
        ],
    },
}


# ── Pydantic models ──────────────────────────────────────────

class ChannelConfigBody(BaseModel):
    enabled: bool = True
    config: Dict[str, str] = {}


# ── 内部工具函数 ─────────────────────────────────────────────

def _extract_gateway_payload(result: dict) -> Optional[dict]:
    """从 manager.send_request 返回值中提取 Gateway RPC payload。"""
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if isinstance(data, dict) and "error" in data:
        logger.warning("Gateway RPC error: %s", data)
        return None
    return data if isinstance(data, dict) else None


def _parse_channel_accounts(gw_payload: dict) -> dict[str, dict]:
    """
    从 channels.status 的 Gateway payload 中提取每个渠道的账号状态。
    返回 {channel_id: {connected, running, lastError, accounts: [...]}}
    """
    accounts_map = gw_payload.get("channelAccounts", {})
    result: dict[str, dict] = {}

    for channel_id, accounts in accounts_map.items():
        if not isinstance(accounts, list):
            continue
        any_connected = False
        any_running = False
        last_error = ""
        acct_list = []
        for acct in accounts:
            if not isinstance(acct, dict):
                continue
            any_connected = any_connected or acct.get("connected", False)
            any_running = any_running or acct.get("running", False)
            if acct.get("lastError"):
                last_error = acct["lastError"]
            acct_list.append({
                "accountId": acct.get("accountId", "default"),
                "connected": acct.get("connected", False),
                "running": acct.get("running", False),
                "lastError": acct.get("lastError", ""),
            })
        result[channel_id] = {
            "connected": any_connected,
            "running": any_running,
            "lastError": last_error,
            "accounts": acct_list,
        }

    return result


async def _gateway_rpc(device_id: str, method: str, params: dict = None, timeout: float = 15.0) -> dict:
    """调用 Gateway RPC 并返回 payload（或 error dict）。"""
    try:
        result = await manager.send_request(device_id, method, params or {}, timeout=timeout)
        payload = _extract_gateway_payload(result)
        if payload is None:
            return {"error": f"{method} returned no data"}
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Gateway RPC %s failed: %s", method, e)
        return {"error": str(e)}


async def _config_patch(device_id: str, patch_obj: dict) -> dict:
    """
    通过 config.get + config.patch 原子地修改 openclaw.json。
    patch_obj 是要 merge 进去的对象（JSON merge-patch 语义）。
    """
    cfg = await _gateway_rpc(device_id, "config.get", {})
    if "error" in cfg:
        return cfg

    base_hash = cfg.get("hash", "")
    if not base_hash:
        return {"error": "config.get returned no hash"}

    raw = json.dumps(patch_obj, ensure_ascii=False)
    patch_result = await _gateway_rpc(device_id, "config.patch", {
        "raw": raw,
        "baseHash": base_hash,
        "restartDelayMs": 1500,
    }, timeout=20.0)
    return patch_result


# ── API 端点 ─────────────────────────────────────────────────

@router.get("/{device_id}")
async def get_channels(device_id: str, request: Request = None):
    """获取设备的所有频道及其 Gateway 实时状态"""
    db = get_db()
    await _require_user_device(db, request, device_id)

    gw_status: dict[str, dict] = {}
    try:
        payload = await _gateway_rpc(device_id, "channels.status")
        if "error" not in payload:
            gw_status = _parse_channel_accounts(payload)
    except Exception as e:
        logger.warning("channels.status failed: %s", e)

    result_list = []
    for channel_id, info in CHANNEL_TYPES.items():
        live = gw_status.get(channel_id, {})
        result_list.append({
            "id": channel_id,
            "name": info["name"],
            "icon": info.get("icon", channel_id),
            "color": info.get("color", "#667eea"),
            "desc": info.get("desc", ""),
            "native": info.get("native", False),
            "comingSoon": info.get("coming_soon", False),
            "configFields": info.get("config_fields", []),
            "connected": live.get("connected", False),
            "running": live.get("running", False),
            "lastError": live.get("lastError", ""),
            "accounts": live.get("accounts", []),
            "configured": channel_id in gw_status,
        })

    return {"success": True, "channels": result_list}


@router.post("/{device_id}/{channel_id}")
async def configure_channel(
    device_id: str,
    channel_id: str,
    body: ChannelConfigBody,
    request: Request = None,
):
    """
    配置渠道 — 通过 config.patch 将凭据写入 openclaw.json。
    Gateway 自动重启后渠道会自行连接。
    """
    if channel_id not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail=f"Unsupported channel: {channel_id}")

    info = CHANNEL_TYPES[channel_id]

    if not info.get("native"):
        raise HTTPException(status_code=400, detail=f"{channel_id} 是插件渠道，暂不支持在线配置")
    if info.get("coming_soon"):
        raise HTTPException(status_code=400, detail=f"{channel_id} 即将支持，敬请期待")

    required = [f["key"] for f in info.get("config_fields", [])]
    missing = [k for k in required if not body.config.get(k)]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填字段: {missing}")

    db = get_db()
    await _require_user_device(db, request, device_id)

    key_map = info.get("config_key_map", {})
    channel_cfg: dict[str, Any] = {}
    for ui_key, gw_key in key_map.items():
        val = body.config.get(ui_key, "")
        if val:
            channel_cfg[gw_key] = val

    if not body.enabled:
        channel_cfg["enabled"] = False

    patch = {"channels": {channel_id: channel_cfg}}
    result = await _config_patch(device_id, patch)

    if "error" in result:
        return {"success": False, "error": result["error"]}

    return {
        "success": True,
        "message": f"{info['name']} 配置已写入，Gateway 正在重启",
        "channel": {"id": channel_id, "name": info["name"]},
    }


@router.delete("/{device_id}/{channel_id}")
async def delete_channel(device_id: str, channel_id: str, request: Request = None):
    """删除渠道配置 — 通过 config.patch 将渠道节点设为 null"""
    if channel_id not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail=f"Unsupported channel: {channel_id}")

    db = get_db()
    await _require_user_device(db, request, device_id)

    patch = {"channels": {channel_id: None}}
    result = await _config_patch(device_id, patch)

    if "error" in result:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"{CHANNEL_TYPES[channel_id]['name']} 已移除"}


@router.post("/{device_id}/{channel_id}/disconnect")
async def disconnect_channel(device_id: str, channel_id: str, request: Request = None):
    """断开渠道连接 — 调用 channels.logout"""
    db = get_db()
    await _require_user_device(db, request, device_id)

    result = await _gateway_rpc(device_id, "channels.logout", {"channel": channel_id})

    if "error" in result:
        return {"success": False, "error": result["error"]}

    return {"success": True, "message": f"{channel_id} 已断开"}


@router.get("/{device_id}/capabilities")
async def get_channel_capabilities(device_id: str, request: Request = None):
    """获取 Gateway 原始 channels.status 数据"""
    db = get_db()
    await _require_user_device(db, request, device_id)

    payload = await _gateway_rpc(device_id, "channels.status")
    if "error" in payload:
        return {"success": False, "error": payload["error"]}
    return {"success": True, "capabilities": payload}


# ── 设备前缀路由（小程序调用）──────────────────────────────

@device_router.get("/{device_id}/channels")
async def device_get_channels(device_id: str, request: Request = None):
    return await get_channels(device_id, request)


@device_router.post("/{device_id}/channels/{channel_id}")
async def device_configure_channel(
    device_id: str,
    channel_id: str,
    body: ChannelConfigBody = None,
    request: Request = None,
):
    return await configure_channel(device_id, channel_id, body or ChannelConfigBody(), request)


@device_router.post("/{device_id}/channels/{channel_id}/disconnect")
async def device_disconnect_channel(device_id: str, channel_id: str, request: Request = None):
    return await disconnect_channel(device_id, channel_id, request)


@device_router.delete("/{device_id}/channels/{channel_id}")
async def device_delete_channel(device_id: str, channel_id: str, request: Request = None):
    return await delete_channel(device_id, channel_id, request)
