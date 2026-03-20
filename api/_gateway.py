"""Gateway RPC 公共工具 — 消除各 API 文件的重复样板"""
import json
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from api.proxy import _require_user_device
from app.core.supabase import get_db
from app.core.websocket import manager


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def rpc_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 manager.send_request 的返回结构：{status, request_id, data}"""
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def rpc_error_text(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    err = payload.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()
    if isinstance(err, dict):
        for key in ("message", "msg", "detail", "code"):
            text = norm_text(err.get(key))
            if text:
                return text
        try:
            return json.dumps(err, ensure_ascii=False)
        except Exception:
            return str(err)
    if payload.get("ok") is False:
        return "RPC request failed"
    return ""


def rpc_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 {payload:{...}} 或直接业务体两种响应形态"""
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("payload"), dict):
        return payload.get("payload") or {}
    return payload


async def read_json_body(request: Request) -> Dict[str, Any]:
    if not request:
        return {}
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


async def resolve_device_id(device_id: Optional[str], request: Request, body: Dict[str, Any] = None) -> str:
    did = norm_text(device_id)
    if did:
        return did
    if isinstance(body, dict):
        from_body = norm_text(body.get("device_id"))
        if from_body:
            return from_body
    parsed = await read_json_body(request)
    return norm_text(parsed.get("device_id"))


async def require_user_device_access(request: Request, device_id: str):
    """统一执行设备归属鉴权。"""
    db = get_db()
    await _require_user_device(db, request, device_id)


async def gateway_rpc(
    device_id: str,
    method: str,
    params: dict | None = None,
    *,
    timeout: float | None = None,
    offline_result: dict | None = None,
) -> dict:
    """
    调用 Gateway RPC，返回 result["data"]（dict），统一处理离线检查和异常。

    - offline_result 不为 None 时，设备离线返回该值（软降级）；
      否则抛出 503 HTTPException（硬失败）。
    - HTTPException 原样透传；其他异常包装为 500。
    """
    if not manager.is_connected(device_id):
        if offline_result is not None:
            return offline_result
        raise HTTPException(status_code=503, detail=f"设备 {device_id} 未连接")
    try:
        kwargs: dict[str, Any] = {}
        if timeout is not None:
            kwargs["timeout"] = timeout
        result = await manager.send_request(device_id, method, params or {}, **kwargs)
        return result.get("data") or {}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
