"""
模型管理 API - 平台模型 + 自定义模型
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger(__name__)


# 支持的平台模型
PLATFORM_MODELS = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI", "enabled": True},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI", "enabled": True},
    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "OpenAI", "enabled": False},
    {"id": "claude-sonnet-4-6", "name": "Claude Sonnet 4-6", "provider": "Anthropic", "enabled": True},
    {"id": "claude-opus-4-5", "name": "Claude Opus 4-5", "provider": "Anthropic", "enabled": False},
    {"id": "claude-haiku-3-5", "name": "Claude Haiku 3.5", "provider": "Anthropic", "enabled": False},
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek", "enabled": False},
    {"id": "deepseek-coder", "name": "DeepSeek Coder", "provider": "DeepSeek", "enabled": False},
    {"id": "moonshot-v1", "name": "Moonshot V1", "provider": "Moonshot", "enabled": False},
    {"id": "glm-4", "name": "GLM-4", "provider": "智谱 AI", "enabled": False},
    {"id": "qwen-turbo", "name": "Qwen Turbo", "provider": "阿里云", "enabled": False},
    {"id": "minimax", "name": "MiniMax", "provider": "MiniMax", "enabled": False},
]


# 服务商配置
PROVIDERS = {
    "openai": {"name": "OpenAI", "baseUrl": "https://api.openai.com/v1"},
    "anthropic": {"name": "Anthropic", "baseUrl": "https://api.anthropic.com"},
    "deepseek": {"name": "DeepSeek", "baseUrl": "https://api.deepseek.com/v1"},
    "moonshot": {"name": "Moonshot", "baseUrl": "https://api.moonshot.cn/v1"},
    "zhipu": {"name": "智谱 AI", "baseUrl": "https://open.bigmodel.cn/api/paas/v4"},
    "qianwen": {"name": "阿里云", "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
    "minimax": {"name": "MiniMax", "baseUrl": "https://api.minimax.chat/v1"},
}


class CustomModel(BaseModel):
    """自定义模型"""
    id: str
    name: str
    provider: str
    providerName: str
    apiKey: str
    baseUrl: str
    model: str
    priority: bool = False


class CustomModelCreate(BaseModel):
    """创建自定义模型"""
    name: str
    provider: str
    apiKey: str
    baseUrl: str = ""
    model: str
    priority: bool = False


class CustomModelUpdate(BaseModel):
    """更新自定义模型"""
    name: Optional[str] = None
    provider: Optional[str] = None
    apiKey: Optional[str] = None
    baseUrl: Optional[str] = None
    model: Optional[str] = None
    priority: Optional[bool] = None


# 内存存储
_platform_models = {k: v.copy() for k, v in zip([p["id"] for p in PLATFORM_MODELS], PLATFORM_MODELS)}
_custom_models: Dict[str, List[CustomModel]] = {}


def _get_custom_models(device_id: str = "default") -> List[CustomModel]:
    """获取自定义模型"""
    if device_id not in _custom_models:
        _custom_models[device_id] = []
    return _custom_models[device_id]


# ========== 平台模型 API ==========

@router.get("/platform")
async def get_platform_models():
    """获取平台模型列表"""
    models = list(_platform_models.values())
    return {
        "success": True,
        "models": models
    }


@router.patch("/platform/{model_id}")
async def update_platform_model(model_id: str, enabled: bool = None):
    """更新平台模型"""
    if model_id not in _platform_models:
        raise HTTPException(status_code=404, detail="Model not found")
    
    if enabled is not None:
        _platform_models[model_id]["enabled"] = enabled
    
    # 检查启用数量
    enabled_count = sum(1 for m in _platform_models.values() if m.get("enabled"))
    if enabled and enabled_count > 6:
        raise HTTPException(status_code=400, detail="最多启用 6 个模型")
    
    return {
        "success": True,
        "model": _platform_models[model_id]
    }


# ========== 自定义模型 API ==========

@router.get("/custom")
async def get_custom_models(device_id: str = "default"):
    """获取自定义模型列表"""
    models = _get_custom_models(device_id)
    return {
        "success": True,
        "models": [m.model_dump() for m in models]
    }


@router.post("/custom")
async def create_custom_model(
    device_id: str = "default",
    model: CustomModelCreate = None
):
    """创建自定义模型"""
    if model is None:
        raise HTTPException(status_code=400, detail="Request body required")
    
    # 验证服务商
    if model.provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {model.provider}")
    
    # 获取服务商默认 URL
    provider_info = PROVIDERS[model.provider]
    base_url = model.baseUrl or provider_info["baseUrl"]
    
    # 生成 ID
    new_id = str(uuid.uuid4())[:8]
    
    custom_model = CustomModel(
        id=new_id,
        name=model.name,
        provider=model.provider,
        providerName=provider_info["name"],
        apiKey=model.apiKey,
        baseUrl=base_url,
        model=model.model,
        priority=model.priority
    )
    
    models = _get_custom_models(device_id)
    
    # 如果设为优先，取消其他优先
    if custom_model.priority:
        for m in models:
            m.priority = False
    
    models.append(custom_model)
    
    return {
        "success": True,
        "model": custom_model.model_dump()
    }


@router.patch("/custom/{model_id}")
async def update_custom_model(
    device_id: str = "default",
    model_id: str = None,
    update: CustomModelUpdate = None
):
    """更新自定义模型"""
    if update is None or model_id is None:
        raise HTTPException(status_code=400, detail="Invalid request")
    
    models = _get_custom_models(device_id)
    model = next((m for m in models if m.id == model_id), None)
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # 更新字段
    if update.name is not None:
        model.name = update.name
    if update.provider is not None:
        if update.provider not in PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unsupported provider: {update.provider}")
        model.provider = update.provider
        model.providerName = PROVIDERS[update.provider]["name"]
    if update.apiKey is not None:
        model.apiKey = update.apiKey
    if update.baseUrl is not None:
        model.baseUrl = update.baseUrl
    if update.model is not None:
        model.model = update.model
    if update.priority is not None:
        # 如果设为优先，取消其他优先
        if update.priority:
            for m in models:
                m.priority = False
        model.priority = update.priority
    
    return {
        "success": True,
        "model": model.model_dump()
    }


@router.delete("/custom/{model_id}")
async def delete_custom_model(device_id: str = "default", model_id: str = None):
    """删除自定义模型"""
    if model_id is None:
        raise HTTPException(status_code=400, detail="Model ID required")
    
    models = _get_custom_models(device_id)
    original_count = len(models)
    models = [m for m in models if m.id != model_id]
    
    if len(models) == original_count:
        raise HTTPException(status_code=404, detail="Model not found")
    
    _custom_models[device_id] = models
    
    return {"success": True}


# ========== 通用 API ==========

@router.get("/providers")
async def get_providers():
    """获取支持的服务商列表"""
    return {
        "success": True,
        "providers": [
            {"id": k, "name": v["name"], "baseUrl": v["baseUrl"]}
            for k, v in PROVIDERS.items()
        ]
    }


@router.get("")
async def get_all_models(device_id: str = "default"):
    """获取所有模型（平台 + 自定义）"""
    platform = list(_platform_models.values())
    custom = _get_custom_models(device_id)
    
    return {
        "success": True,
        "platformModels": platform,
        "customModels": [m.model_dump() for m in custom]
    }
