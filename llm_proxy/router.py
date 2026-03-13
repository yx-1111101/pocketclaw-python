"""LLM 代理路由"""
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from llm_proxy.auth import DeviceAuth, verify_device_auth
from llm_proxy.providers import registry, resolve
from llm_proxy.redis_db import get_device as cache_get_device, set_device as cache_set_device
from llm_proxy.supabase_client import get_device as db_get_device

router = APIRouter(prefix="/llm", tags=["LLM代理"])


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: list
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


async def _get_device(device_id: str) -> Optional[dict]:
    """Cache-aside: Redis (60s TTL) → Supabase."""
    device = await cache_get_device(device_id)
    if device is None:
        device = await db_get_device(device_id)
        if device:
            await cache_set_device(device_id, device)
    return device


@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: ChatRequest,
    auth_info: Tuple[str, int, str] = Depends(verify_device_auth),
):
    """
    LLM 聊天补全接口

    Headers:
        X-Device-Id:   设备 ID
        X-Timestamp:   Unix 时间戳（秒）
        Authorization: HMAC-SHA256 <signature>
    """
    device_id, timestamp, signature = auth_info

    # 1. 查找设备（Redis → Supabase）
    device = await _get_device(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # 2. 验签 — key = bytes.fromhex(device_secret_hash)，无需持有明文 secret
    device_secret_hash = device.get("device_secret_hash")
    if not device_secret_hash:
        raise HTTPException(
            status_code=401,
            detail="Device not registered. Please send a heartbeat first.",
        )

    if not DeviceAuth.verify_signature(device_id, timestamp, signature, device_secret_hash):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. 路由
    try:
        provider, route = resolve(request.model or "", provider_hint=request.provider)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 4. 合并参数
    temperature = request.temperature if request.temperature is not None else route.temperature
    max_tokens = request.max_tokens if request.max_tokens is not None else route.max_tokens

    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if request.stream:
        kwargs["stream"] = request.stream

    # 5. 调用 LLM
    try:
        result = await provider.chat_completion(
            messages=request.messages,
            model=route.model,
            timeout=route.timeout,
            **kwargs,
        )
        return ChatResponse(success=True, data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM API error: {str(e)}")


@router.get("/providers")
async def list_providers():
    return {"success": True, "providers": registry.list_providers()}


@router.get("/models")
async def list_models():
    return {"success": True, "models": registry.list_models()}


@router.get("/health")
async def health_check():
    return {"ok": True, "service": "llm_proxy"}
