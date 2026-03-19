"""
模型管理 API - 调用真实 Gateway RPC
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid
import logging

from app.core.gateway_rpc import call_gateway_rpc_sync

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger(__name__)


# ========== 平台模型 API ==========

@router.get("/platform")
async def get_platform_models():
    """获取平台模型列表 - 从 Gateway 获取"""
    try:
        result = call_gateway_rpc_sync("models.list")
        if "error" in result:
            logger.error(f"Failed to get models: {result}")
            return {"success": False, "error": result.get("error"), "models": []}
        
        models = result.get("models", [])
        # 添加 enabled 字段（基于 tags）
        for m in models:
            m["enabled"] = "configured" in m.get("tags", [])
        
        return {"success": True, "models": models}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "models": []}


@router.patch("/platform/{model_id}")
async def update_platform_model(model_id: str, enabled: bool = None):
    """更新平台模型 - 暂不支持通过 RPC 修改"""
    if enabled is not None:
        # TODO: 通过 config.set 实现
        pass
    return {"success": True, "message": "Model configuration via Gateway not implemented yet"}


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
async def get_all_models(device_id: str = "default"):
    """获取所有模型（平台 + 自定义）"""
    # 平台模型从 Gateway 获取
    platform_result = call_gateway_rpc_sync("models.list")
    platform = platform_result.get("models", []) if isinstance(platform_result, dict) else []
    
    # 自定义模型从本地获取
    custom = _get_custom_models(device_id)
    
    return {
        "success": True,
        "platformModels": platform,
        "customModels": custom
    }
