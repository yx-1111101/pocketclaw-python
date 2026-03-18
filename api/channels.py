"""
Channel management API
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

router = APIRouter(prefix="/channels", tags=["channels"])
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


# 内存存储（生产环境应使用数据库）
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
async def get_channels(device_id: str):
    """获取设备的所有频道"""
    channels = _get_device_channels(device_id)
    
    result = []
    for channel_id, channel_data in channels.items():
        channel_info = CHANNEL_TYPES.get(channel_id, {})
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
async def configure_channel(device_id: str, channel_id: str, config: ChannelConfig):
    """配置频道"""
    if channel_id not in CHANNEL_TYPES:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not supported")
    
    channels = _get_device_channels(device_id)
    
    # 验证配置
    required_fields = [f["key"] for f in CHANNEL_TYPES[channel_id].get("config_fields", [])]
    missing = [f for f in required_fields if f not in config.config or not config.config[f]]
    if missing and config.enabled:
        raise HTTPException(status_code=400, detail=f"Missing required fields: {missing}")
    
    # 保存配置
    channels[channel_id] = config
    
    # TODO: 实际连接到设备 Gateway 进行配置
    # 模拟连接成功
    if config.enabled and config.config:
        channels[channel_id].connected = True
    
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
async def update_channel(device_id: str, channel_id: str, config: ChannelConfig):
    """更新频道配置"""
    return await configure_channel(device_id, channel_id, config)


@router.delete("/{device_id}/{channel_id}")
async def delete_channel(device_id: str, channel_id: str):
    """删除频道配置"""
    channels = _get_device_channels(device_id)
    
    if channel_id in channels:
        channels[channel_id] = ChannelConfig(enabled=False, config={}, connected=False)
    
    return {"success": True}


@router.post("/{device_id}/{channel_id}/connect")
async def connect_channel(device_id: str, channel_id: str):
    """连接频道"""
    channels = _get_device_channels(device_id)
    
    if channel_id not in channels:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    channel = channels[channel_id]
    
    if not channel.enabled:
        raise HTTPException(status_code=400, detail="Channel is not enabled")
    
    # TODO: 实际调用设备 Gateway 进行连接
    # 模拟连接
    channel.connected = True
    
    return {"success": True, "connected": True}


@router.post("/{device_id}/{channel_id}/disconnect")
async def disconnect_channel(device_id: str, channel_id: str):
    """断开频道连接"""
    channels = _get_device_channels(device_id)
    
    if channel_id in channels:
        channels[channel_id].connected = False
    
    return {"success": True}
