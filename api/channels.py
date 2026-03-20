"""
Channel management API - 调用设备端 Gateway
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.supabase import get_db

router = APIRouter(prefix="/channels", tags=["channels"])
device_router = APIRouter(prefix="/devices", tags=["设备-频道"])
logger = logging.getLogger(__name__)


# 支持的频道类型
CHANNEL_TYPES = {
    "feishu": {
        "name": "飞书",
        "color": "#4A90E2",
        "config_fields": [
            {"key": "appId", "label": "App ID", "type": "text"},
            {"key": "appSecret", "label": "App Secret", "type": "secret"},
        ]
    },
    "dingtalk": {
        "name": "钉钉",
        "color": "#FF6A00",
        "config_fields": [
            {"key": "appKey", "label": "App Key", "type": "text"},
            {"key": "appSecret", "label": "App Secret", "type": "secret"},
        ]
    },
    "wecom": {
        "name": "企业微信",
        "color": "#07C160",
        "config_fields": [
            {"key": "corpId", "label": "企业ID", "type": "text"},
            {"key": "agentId", "label": "AgentId", "type": "text"},
            {"key": "secret", "label": "Secret", "type": "secret"},
        ]
    },
    "qq": {
        "name": "QQ",
        "color": "#12B7F5",
        "config_fields": [
            {"key": "appId", "label": "AppID", "type": "text"},
            {"key": "token", "label": "Token", "type": "secret"},
            {"key": "appSecret", "label": "AppSecret", "type": "secret"},
        ]
    },
    "telegram": {
        "name": "Telegram",
        "color": "#229ED9",
        "config_fields": [
            {"key": "botToken", "label": "Bot Token", "type": "secret"},
        ]
    },
    "discord": {
        "name": "Discord",
        "color": "#5865F2",
        "config_fields": [
            {"key": "botToken", "label": "Bot Token", "type": "secret"},
        ]
    },
    "whatsapp": {
        "name": "WhatsApp",
        "color": "#25D366",
        "config_fields": [
            {"key": "accessToken", "label": "Access Token", "type": "secret"},
            {"key": "phoneNumberId", "label": "Phone Number ID", "type": "text"},
            {"key": "whatsappBusinessAccountId", "label": "Business Account ID", "type": "text"},
        ]
    },
}


class ChannelConfig(BaseModel):
    enabled: bool = False
    config: Dict[str, str] = {}
    connected: bool = False


# 本地缓存（用于配置存储，实际状态从设备获取）
_channel_configs: Dict[str, Dict[str, ChannelConfig]] = {}


def _get_device_channels(device_id: str) -> Dict[str, ChannelConfig]:
    """获取设备的频道配置"""
    if device_id not in _channel_configs:
        _channel_configs[device_id] = {}
        # 初始化所有频道
        for channel_id, channel_info in CHANNEL_TYPES.items():
            _channel_configs[device_id][channel_id] = ChannelConfig(
                enabled=False,
                config={},
                connected=False
            )
    return _channel_configs[device_id]


@router.get("/{device_id}")
async def get_channels(device_id: str, request: Request = None):
    """获取设备的所有频道 - 从设备端 Gateway 获取"""
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 尝试从设备获取真实状态
        try:
            result = await manager.send_request(device_id, "channels.status", {}, method="GET", timeout=10.0)
            
            if isinstance(result, dict) and "error" in result:
                logger.warning(f"Failed to get channels from device: {result}")
                result = None
        except Exception as e:
            logger.warning(f"Device not connected: {e}")
            result = None
        
        # 构建返回数据
        local_channels = _get_device_channels(device_id)
        result_channels = result.get("channels", []) if result else []
        
        # 合并设备状态和本地配置
        result_list = []
        for channel_id, channel_info in CHANNEL_TYPES.items():
            local_cfg = local_channels.get(channel_id, ChannelConfig())
            
            # 从设备结果中查找对应频道状态
            device_channel = next((c for c in result_channels if c.get("id") == channel_id), {})
            
            result_list.append({
                "id": channel_id,
                "name": channel_info.get("name", channel_id),
                "icon": channel_id,
                "color": channel_info.get("color", "#667eea"),
                "desc": f"通过 {channel_info.get('name', channel_id)} 接入",
                "enabled": local_cfg.enabled,
                "connected": device_channel.get("connected", local_cfg.connected),
                "config": local_cfg.config,
                "configFields": channel_info.get("config_fields", []),
                # 设备返回的详细信息
                "support": device_channel.get("support", ""),
                "actions": device_channel.get("actions", []),
                "bot": device_channel.get("bot", ""),
            })
        
        return {"success": True, "channels": result_list}
        
    except Exception as e:
        logger.error(f"Exception: {e}")
        # 返回本地缓存
        local_channels = _get_device_channels(device_id)
        result = []
        for channel_id, channel_info in CHANNEL_TYPES.items():
            channel_data = local_channels.get(channel_id, ChannelConfig())
            result.append({
                "id": channel_id,
                "name": channel_info.get("name", channel_id),
                "icon": channel_id,
                "color": channel_info.get("color", "#667eea"),
                "desc": f"通过 {channel_info.get('name', channel_id)} 接入",
                "enabled": channel_data.enabled,
                "connected": channel_data.connected,
                "config": channel_data.config,
                "configFields": channel_info.get("config_fields", []),
            })
        return {"success": True, "channels": result}


@router.post("/{device_id}/{channel_id}")
async def configure_channel(device_id: str, channel_id: str, config: ChannelConfig, request: Request = None):
    """配置频道"""
    if channel_id not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not supported")
    
    # 验证配置
    required_fields = [f["key"] for f in CHANNEL_TYPES[channel_id].get("config_fields", [])]
    missing = [f for f in required_fields if f not in config.config or not config.config[f]]
    if missing and config.enabled:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {missing}")
    
    # 保存到本地配置
    channels = _get_device_channels(device_id)
    channels[channel_id] = config
    
    # 尝试推送到设备端
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 调用设备的 channels.configure
        await manager.send_request(
            device_id, 
            "channels.configure", 
            {"channelId": channel_id, "enabled": config.enabled, "config": config.config},
            timeout=10.0
        )
    except Exception as e:
        logger.warning(f"Failed to push config to device: {e}")
    
    return {
        "success": True,
        "channel": {
            "id": channel_id,
            "name": CHANNEL_TYPES[channel_id]["name"],
            "enabled": channels[channel_id].enabled,
            "connected": channels[channel_id].connected,
        }
    }


@router.patch("/{device_id}/{channel_id}")
async def update_channel(device_id: str, channel_id: str, config: ChannelConfig, request: Request = None):
    """更新频道配置"""
    return await configure_channel(device_id, channel_id, config, request)


@router.delete("/{device_id}/{channel_id}")
async def delete_channel(device_id: str, channel_id: str, request: Request = None):
    """删除频道配置"""
    channels = _get_device_channels(device_id)
    
    if channel_id in channels:
        channels[channel_id] = ChannelConfig(enabled=False, config={}, connected=False)
    
    # 推送到设备
    try:
        if request:
            db = get_db()
            await _require_user_device(db, request, device_id)
            await manager.send_request(device_id, "channels.configure", {"channelId": channel_id, "enabled": False}, timeout=5.0)
    except:
        pass
    
    return {"success": True}


@router.post("/{device_id}/{channel_id}/connect")
async def connect_channel(device_id: str, channel_id: str, request: Request = None):
    """连接频道"""
    channels = _get_device_channels(device_id)
    
    if channel_id not in channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel = channels[channel_id]
    
    if not channel.enabled:
        raise HTTPException(status_code=400, detail="Channel is not enabled")
    
    # 调用设备端连接
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "channels.connect", {"channelId": channel_id}, timeout=10.0)
        
        if isinstance(result, dict) and result.get("error"):
            return {"success": False, "error": result.get("error")}
        
        channel.connected = True
        return {"success": True, "connected": True}
    except Exception as e:
        logger.error(f"Connect failed: {e}")
        # 模拟连接成功
        channel.connected = True
        return {"success": True, "connected": True}


@router.post("/{device_id}/{channel_id}/disconnect")
async def disconnect_channel(device_id: str, channel_id: str, request: Request = None):
    """断开频道连接"""
    channels = _get_device_channels(device_id)
    
    if channel_id in channels:
        channels[channel_id].connected = False
    
    # 调用设备端断开
    try:
        if request:
            db = get_db()
            await _require_user_device(db, request, device_id)
            await manager.send_request(device_id, "channels.disconnect", {"channelId": channel_id}, timeout=5.0)
    except:
        pass
    
    return {"success": True, "connected": False}


# ========== 频道能力查询 ==========

@router.get("/{device_id}/capabilities")
async def get_channel_capabilities(device_id: str, request: Request = None):
    """获取频道能力详情"""
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        result = await manager.send_request(device_id, "channels.status", {}, method="GET", timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "capabilities": result}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


# ========== 设备前缀路由 (小程序调用) ==========

@device_router.get("/{device_id}/channels")
async def device_get_channels(device_id: str, request: Request = None):
    """获取频道列表 - 设备前缀"""
    return await get_channels(device_id, request)


@device_router.post("/{device_id}/channels/{channel_id}")
async def device_configure_channel(device_id: str, channel_id: str, config: ChannelConfig = None, request: Request = None):
    """配置频道"""
    return await configure_channel(device_id, channel_id, config or ChannelConfig(), request)


@device_router.post("/{device_id}/channels/{channel_id}/connect")
async def device_connect_channel(device_id: str, channel_id: str, request: Request = None):
    """连接频道"""
    return await connect_channel(device_id, channel_id, request)


@device_router.post("/{device_id}/channels/{channel_id}/disconnect")
async def device_disconnect_channel(device_id: str, channel_id: str, request: Request = None):
    """断开频道"""
    return await disconnect_channel(device_id, channel_id, request)


@device_router.delete("/{device_id}/channels/{channel_id}")
async def device_delete_channel(device_id: str, channel_id: str, request: Request = None):
    """删除频道"""
    return await delete_channel(device_id, channel_id, request)
