"""LLM 代理路由"""
from typing import AsyncIterator, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from llm_proxy.auth import verify_device_auth
from llm_proxy.exchange_rate import get_usd_to_cny, convert_to_cny
from llm_proxy.providers import registry, resolve
from llm_proxy.supabase_client import get_device_binding, log_proxy_request, get_pricing
from llm_proxy.usage_stats import calculator

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


@router.post("/chat/completions")
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
    device_id, _timestamp, _signature = auth_info

    # 1. Check device_bindings — if device_id exists in the table, allow the request
    binding = await get_device_binding(device_id)
    if not binding:
        print(f"[auth] 401 device not in device_bindings | device={device_id}")
        raise HTTPException(status_code=401, detail="Device not authorized")

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

    # 5a. 流式响应
    if request.stream:
        async def sse_generator() -> AsyncIterator[str]:
            try:
                line_count = 0
                async for line in provider.chat_completion_stream(
                    messages=request.messages,
                    model=route.model,
                    timeout=route.timeout,
                    **kwargs,
                ):
                    line_count += 1
                    if line_count <= 3:
                        print(f"[stream] line {line_count}: {repr(line)}")
                    yield line + "\n"
                print(f"[stream] done, total lines={line_count}")
            except Exception as e:
                print(f"[stream] error: {e}")
                yield f"data: {{'error': '{str(e)}'}}\n\n"

        print(f"[llm_proxy] stream=True provider={route.provider} model={route.model}")
        return StreamingResponse(sse_generator(), media_type="text/event-stream")

    # 5b. 非流式响应
    print(f"[llm_proxy] stream=False provider={route.provider} model={route.model}")
    try:
        result = await provider.chat_completion(
            messages=request.messages,
            model=route.model,
            timeout=route.timeout,
            **kwargs,
        )
        print(f"[llm_proxy] non-stream result keys={list(result.keys()) if isinstance(result, dict) else type(result)}")

        # 6. 记录使用统计
        try:
            extractor = calculator.get_extractor(provider.cfg.request_type)
            usage = extractor.extract_usage(result)

            cost_original = 0.0
            cost_currency = "USD"
            cost_cny = 0.0

            pricing_data = await get_pricing(route.model, route.provider, provider.cfg.request_type)
            if pricing_data:
                cost_original, cost_currency = calculator.calculate_cost(usage, pricing_data)
                usd_to_cny = await get_usd_to_cny()
                cost_cny = convert_to_cny(cost_original, cost_currency, usd_to_cny)

            user_id = binding.get("user_id")
            await log_proxy_request(
                user_id=user_id,
                device_id=device_id,
                model=route.model,
                provider=route.provider,
                request_type=provider.cfg.request_type,
                usage=usage,
                cost_original=cost_original,
                cost_currency=cost_currency,
                cost_cny=cost_cny,
            )
        except Exception as log_error:
            print(f"[llm_proxy] Failed to log usage: {log_error}")

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
