"""LLM 代理路由"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Tuple
from pydantic import BaseModel

from llm_proxy.redis_db import get_db
from llm_proxy.auth import verify_device_auth, DeviceAuth
from llm_proxy.providers import resolve, registry


router = APIRouter(prefix="/llm", tags=["LLM代理"])


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: list
    model: Optional[str] = None       # None → use default from routing.yaml
    provider: Optional[str] = None    # None → use routing.yaml rule
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = False


class ChatResponse(BaseModel):
    """聊天响应"""
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


@router.post("/chat/completions", response_model=ChatResponse)
async def chat_completions(
    request: ChatRequest,
    auth_info: Tuple[str, int, str] = Depends(verify_device_auth)
):
    """
    LLM 聊天补全接口

    需要设备认证 Headers:
        X-Device-Id: 设备 ID
        X-Timestamp: Unix 时间戳（秒）
        Authorization: HMAC-SHA256 <signature>

    Body:
        model:    模型名（可选，默认使用 routing.yaml 中的 default.model）
        provider: 提供商名（可选，覆盖 routing.yaml 中的路由规则）
        messages, temperature, max_tokens, stream: 标准参数
    """
    device_id, timestamp, signature = auth_info
    db = get_db()

    # 1. 验证设备是否存在
    devices = await db.get("devices", {"device_id": device_id})
    if not devices or isinstance(devices, dict):
        raise HTTPException(status_code=404, detail="Device not found")

    device = devices[0]

    # 2. 获取设备密钥并验证签名
    device_secret = device.get("device_secret")
    if not device_secret:
        raise HTTPException(
            status_code=401,
            detail="Device secret not registered. Please send a heartbeat first to complete device setup.",
        )

    if not DeviceAuth.verify_signature(device_id, timestamp, signature, device_secret):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. 验证设备是否已绑定用户（留空待实现）
    # bindings = await db.get("device_bindings", {"device_id": device["id"]})
    # if not bindings or len(bindings) == 0:
    #     raise HTTPException(status_code=403, detail="Device not bound to any user")

    # 4. 路由：根据 model 名查 routing.yaml，解析出 provider + route
    try:
        model_name = request.model or ""
        provider, route = resolve(model_name, provider_hint=request.provider)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 5. 合并参数（请求体覆盖 YAML 默认值）
    temperature = request.temperature if request.temperature is not None else route.temperature
    max_tokens  = request.max_tokens  if request.max_tokens  is not None else route.max_tokens

    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if request.stream:
        kwargs["stream"] = request.stream

    # 6. 调用 LLM API
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
    """列出可用的 LLM 提供商"""
    return {"success": True, "providers": registry.list_providers()}


@router.get("/models")
async def list_models():
    """列出 routing.yaml 中配置的模型"""
    return {"success": True, "models": registry.list_models()}


@router.get("/health")
async def health_check():
    """健康检查"""
    return {"ok": True, "service": "llm_proxy"}
