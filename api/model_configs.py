"""模型配置 API（云端统一入口，转发到设备 OpenClaw Gateway）"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.supabase import get_db
from app.core.websocket import manager
from api.proxy import _require_user_device

router = APIRouter(prefix="/devices", tags=["模型配置"])

_KEY_FIELDS = ("apiKey", "api_key", "apikey", "token", "accessToken", "secretKey", "key")
_PROVIDER_LABELS = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "google": "Google",
    "gemini": "Google",
    "minimax": "MiniMax",
    "deepseek": "DeepSeek",
    "qwen": "Qwen",
    "glm": "GLM",
    "doubao": "豆包",
    "openrouter": "OpenRouter",
    "groq": "Groq",
    "volcengine": "火山引擎",
    "zhizengzeng": "中转服务",
    "local": "本地模型",
    "model-router": "模型路由",
}


def _rpc_payload(data):
    if not isinstance(data, dict):
        return {}
    payload = data.get("payload")
    if isinstance(payload, dict):
        return payload
    result = data.get("result")
    if isinstance(result, dict):
        return result
    return data


async def _gateway_rpc(device_id: str, method: str, params: Optional[dict] = None, timeout: float = 20.0):
    result = await manager.send_request(device_id, method, params or {}, timeout=timeout)
    payload = _rpc_payload(result.get("data") or {})
    if isinstance(payload, dict):
        if payload.get("ok") is False:
            err = payload.get("error") or payload.get("message") or "gateway request failed"
            raise HTTPException(status_code=502, detail=f"{method} 失败: {err}")
        if payload.get("error"):
            raise HTTPException(status_code=502, detail=f"{method} 失败: {payload.get('error')}")
    return payload if isinstance(payload, dict) else {}


def _mask_key(raw: str) -> str:
    key = str(raw or "").strip()
    if not key:
        return ""
    if len(key) <= 8:
        return f"{key[:2]}{'*' * max(0, len(key) - 2)}"
    return f"{key[:3]}{'*' * max(4, len(key) - 5)}{key[-2:]}"


def _extract_provider_key(provider_cfg: dict) -> str:
    if not isinstance(provider_cfg, dict):
        return ""
    for field in _KEY_FIELDS:
        value = provider_cfg.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    auth = provider_cfg.get("auth")
    if isinstance(auth, dict):
        token = auth.get("token")
        if isinstance(token, str) and token.strip():
            return token.strip()
    return ""


def _pick_key_target(provider_cfg: dict) -> str:
    if not isinstance(provider_cfg, dict):
        return "apiKey"
    for field in _KEY_FIELDS:
        value = provider_cfg.get(field)
        if isinstance(value, str) and value.strip():
            return field
    auth = provider_cfg.get("auth")
    if isinstance(auth, dict):
        token = auth.get("token")
        if isinstance(token, str) and token.strip():
            return "auth.token"
    return "apiKey"


def _extract_active_model(config: dict) -> str:
    if not isinstance(config, dict):
        return ""
    model_cfg = config.get("model")
    if isinstance(model_cfg, dict):
        primary = model_cfg.get("primary")
        if isinstance(primary, str) and primary.strip():
            return primary.strip()
    models_cfg = config.get("models")
    if isinstance(models_cfg, dict):
        primary = models_cfg.get("primary")
        if isinstance(primary, str) and primary.strip():
            return primary.strip()
    runtime = config.get("runtime")
    if isinstance(runtime, dict):
        model = runtime.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    return ""


def _provider_label(provider: str) -> str:
    p = str(provider or "").strip()
    return _PROVIDER_LABELS.get(p.lower(), p or "未知")


@router.get("/{device_id}/model-configs")
async def list_model_configs(device_id: str, request: Request):
    """读取模型列表 + 当前配置的 provider key 状态（统一给小程序使用）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        models_payload = await _gateway_rpc(device_id, "models.list", {"includeAll": True})
        cfg_payload = await _gateway_rpc(device_id, "config.get", {})

        models = models_payload.get("models", [])
        models = models if isinstance(models, list) else []
        services = cfg_payload.get("services", {})
        services = services if isinstance(services, dict) else {}

        provider_order = []
        for item in models:
            if not isinstance(item, dict):
                continue
            provider = str(item.get("provider") or "").strip()
            if provider and provider not in provider_order:
                provider_order.append(provider)
        for provider in services.keys():
            p = str(provider or "").strip()
            if p and p not in provider_order:
                provider_order.append(p)

        providers = []
        for provider in provider_order:
            cfg = services.get(provider, {})
            api_key = _extract_provider_key(cfg)
            providers.append({
                "provider": provider,
                "label": _provider_label(provider),
                "has_key": bool(api_key),
                "api_key_masked": _mask_key(api_key),
            })

        return {
            "success": True,
            "active_model": _extract_active_model(cfg_payload),
            "models": models,
            "providers": providers,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ApiKeyUpsertRequest(BaseModel):
    api_key: str


@router.post("/{device_id}/model-configs/{provider}/apikey")
async def set_provider_apikey(device_id: str, provider: str, body: ApiKeyUpsertRequest, request: Request):
    """设置某个 provider 的 API Key（config.patch）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    key = str(body.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="api_key 不能为空")

    try:
        cfg_payload = await _gateway_rpc(device_id, "config.get", {})
        services = cfg_payload.get("services", {})
        services = services if isinstance(services, dict) else {}
        provider_cfg = services.get(provider, {})
        target = _pick_key_target(provider_cfg)

        if target == "auth.token":
            patch = {"services": {provider: {"auth": {"token": key}}}}
        else:
            patch = {"services": {provider: {target: key}}}

        await _gateway_rpc(device_id, "config.patch", {"patch": patch})
        return {
            "success": True,
            "provider": provider,
            "api_key_masked": _mask_key(key),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}/model-configs/{provider}/apikey")
async def delete_provider_apikey(device_id: str, provider: str, request: Request):
    """删除某个 provider 的 API Key（config.patch with null）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        patch = {
            "services": {
                provider: {
                    "apiKey": None,
                    "api_key": None,
                    "apikey": None,
                    "token": None,
                    "accessToken": None,
                    "secretKey": None,
                    "key": None,
                    "auth": {"token": None},
                }
            }
        }
        await _gateway_rpc(device_id, "config.patch", {"patch": patch})
        return {"success": True, "provider": provider}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ActiveModelRequest(BaseModel):
    model_id: str
    session_key: Optional[str] = None


@router.post("/{device_id}/model-configs/active")
async def set_active_model(device_id: str, body: ActiveModelRequest, request: Request):
    """设置默认模型（config.patch），可选同步覆盖当前会话模型（sessions.patch）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    model_id = str(body.model_id or "").strip()
    if not model_id:
        raise HTTPException(status_code=400, detail="model_id 不能为空")
    try:
        cfg_payload = await _gateway_rpc(device_id, "config.get", {})
        if isinstance(cfg_payload.get("model"), dict):
            patch = {"model": {"primary": model_id}}
        elif isinstance(cfg_payload.get("models"), dict):
            patch = {"models": {"primary": model_id}}
        else:
            patch = {"model": {"primary": model_id}}
        await _gateway_rpc(device_id, "config.patch", {"patch": patch})

        if body.session_key:
            await _gateway_rpc(
                device_id,
                "sessions.patch",
                {"key": body.session_key, "patch": {"model": model_id}},
            )

        return {"success": True, "active_model": model_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
