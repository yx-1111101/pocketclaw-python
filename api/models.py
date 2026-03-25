"""
模型管理 API - 调用设备端 Gateway RPC
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.db import get_db

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger(__name__)


# ========== 平台模型 API ==========

@router.get("/platform")
async def get_platform_models(device_id: str = None, request: Request = None):
    """获取平台模型列表 - 从设备端 Gateway 获取"""
    try:
        if device_id and request:
            # 调用设备的 Gateway
            db = get_db()
            await _require_user_device(db, request, device_id)
            result = await manager.send_request(device_id, "models.list", {}, method="GET")
        else:
            # 没有设备ID，返回错误
            return {"success": False, "error": "device_id required", "models": []}
        
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Failed to get models: {result}")
            return {"success": False, "error": result.get("error"), "models": []}
        
        models = result.get("models", []) if isinstance(result, dict) else []
        # 添加 enabled 字段（基于 tags）
        for m in models:
            m["enabled"] = "configured" in m.get("tags", [])
        
        return {"success": True, "models": models}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "models": []}


@router.patch("/platform/{model_id}")
async def update_platform_model(device_id: str = None, model_id: str = None, enabled: bool = None, request: Request = None):
    """更新平台模型 - 暂不支持"""
    return {"success": True, "message": "Model configuration via device not implemented yet"}


# ========== 自定义模型 API ==========

# 内存存储（生产环境应使用数据库）
_custom_models: Dict[str, List[Dict]] = {}


def _get_custom_models(device_id: str = "default") -> List[Dict]:
    """获取自定义模型"""
    if device_id not in _custom_models:
        _custom_models[device_id] = []
    return _custom_models[device_id]


@router.get("/custom")
async def get_custom_models(device_id: str = "default"):
    """获取自定义模型列表"""
    models = _get_custom_models(device_id)
    return {"success": True, "models": models}


@router.post("/custom")
async def create_custom_model(
    device_id: str = "default",
    name: str = None,
    provider: str = None,
    apiKey: str = None,
    baseUrl: str = "",
    model: str = None,
    priority: bool = False
):
    """创建自定义模型"""
    if not all([name, provider, apiKey, model]):
        return {"success": False, "error": "Missing required fields"}
    
    new_model = {
        "id": str(uuid.uuid4())[:8],
        "name": name,
        "provider": provider,
        "apiKey": apiKey,
        "baseUrl": baseUrl,
        "model": model,
        "priority": priority
    }
    
    models = _get_custom_models(device_id)
    models.append(new_model)
    
    return {"success": True, "model": new_model}


@router.patch("/custom/{model_id}")
async def update_custom_model(
    device_id: str = "default",
    model_id: str = None,
    name: str = None,
    priority: bool = None
):
    """更新自定义模型"""
    models = _get_custom_models(device_id)
    for m in models:
        if m["id"] == model_id:
            if name:
                m["name"] = name
            if priority is not None:
                m["priority"] = priority
            return {"success": True, "model": m}
    return {"success": False, "error": "Model not found"}


@router.delete("/custom/{model_id}")
async def delete_custom_model(device_id: str = "default", model_id: str = None):
    """删除自定义模型"""
    models = _get_custom_models(device_id)
    original_len = len(models)
    models = [m for m in models if m["id"] != model_id]
    
    if len(models) == original_len:
        return {"success": False, "error": "Model not found"}
    
    _custom_models[device_id] = models
    return {"success": True}


# ========== 通用 API ==========

@router.get("/providers")
async def get_providers():
    """获取支持的服务商列表"""
    return {
        "success": True,
        "providers": [
            {"id": "openai", "name": "OpenAI", "baseUrl": "https://api.openai.com/v1"},
            {"id": "anthropic", "name": "Anthropic", "baseUrl": "https://api.anthropic.com"},
            {"id": "deepseek", "name": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1"},
            {"id": "moonshot", "name": "Moonshot", "baseUrl": "https://api.moonshot.cn/v1"},
            {"id": "zhipu", "name": "智谱 AI", "baseUrl": "https://open.bigmodel.cn/api/paas/v4"},
        ]
    }


@router.get("")
async def get_all_models(device_id: str = None, request: Request = None):
    """获取所有模型（平台 + 自定义）"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    # 平台模型从设备端 Gateway 获取
    db = get_db()
    await _require_user_device(db, request, device_id)
    
    try:
        platform_result = await manager.send_request(device_id, "models.list", {}, method="GET")
        platform = platform_result.get("models", []) if isinstance(platform_result, dict) else []
    except Exception as e:
        logger.error(f"Failed to get platform models: {e}")
        platform = []
    
    # 自定义模型从本地获取
    custom = _get_custom_models(device_id)
    
    return {
        "success": True,
        "platformModels": platform,
        "customModels": custom
    }
