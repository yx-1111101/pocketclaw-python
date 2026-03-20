"""Usage 统计 API（顶层 /usage，底层调用设备 Gateway usage.* RPC）"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from api._gateway import (
    read_json_body,
    require_user_device_access,
    resolve_device_id,
    rpc_data,
    rpc_error_text,
    rpc_payload,
)
from app.core.websocket import manager

router = APIRouter(prefix="/usage", tags=["用量统计"])
logger = logging.getLogger(__name__)


def _strip_device_id(data: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(data or {})
    params.pop("device_id", None)
    return params


async def _forward_rpc(
    request: Request,
    method: str,
    *,
    device_id: Optional[str] = None,
    body: Optional[Dict[str, Any]] = None,
    params: Dict[str, Any] = None,
    timeout: float = 15.0,
) -> Dict[str, Any]:
    if not request:
        return {"success": False, "error": "device_id required"}

    did = await resolve_device_id(device_id, request, body)
    if not did:
        return {"success": False, "error": "device_id required"}

    try:
        await require_user_device_access(request, did)
        result = await manager.send_request(did, method, params or {}, timeout=timeout)
        payload = rpc_payload(result)
        err = rpc_error_text(payload)
        if err:
            return {"success": False, "error": err}
        return {"success": True, "data": rpc_data(payload)}
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        return {"success": False, "error": detail or str(e)}


@router.post("/cost")
async def usage_cost_post(device_id: str = None, request: Request = None):
    """usage.cost：获取 token/cost 统计（POST）"""
    body = await read_json_body(request)
    params = _strip_device_id(body)
    try:
        result = await _forward_rpc(
            request=request,
            method="usage.cost",
            device_id=device_id,
            body=body,
            params=params,
            timeout=20.0,
        )
        if not result.get("success"):
            return result
        payload = dict(result.get("data") or {})
        payload["success"] = True
        return payload
    except Exception as e:
        logger.error("[usage.cost] %s", e)
        return {"success": False, "error": str(e)}


@router.get("/cost")
async def usage_cost_get(device_id: str = None, request: Request = None):
    """usage.cost：获取 token/cost 统计（GET）"""
    if not request:
        return {"success": False, "error": "device_id required"}

    query = _strip_device_id(dict(request.query_params) if request.query_params else {})
    try:
        result = await _forward_rpc(
            request=request,
            method="usage.cost",
            device_id=device_id,
            params=query,
            timeout=20.0,
        )
        if not result.get("success"):
            return result
        payload = dict(result.get("data") or {})
        payload["success"] = True
        return payload
    except Exception as e:
        logger.error("[usage.cost:get] %s", e)
        return {"success": False, "error": str(e)}


@router.get("/status")
async def usage_status(device_id: str = None, request: Request = None):
    """usage.status：获取 usage 提供方状态"""
    try:
        result = await _forward_rpc(
            request=request,
            method="usage.status",
            device_id=device_id,
            params={},
        )
        if not result.get("success"):
            return result
        payload = dict(result.get("data") or {})
        payload["success"] = True
        return payload
    except Exception as e:
        logger.error("[usage.status] %s", e)
        return {"success": False, "error": str(e)}


@router.get("/sessions/{session_key}")
async def usage_session(session_key: str, device_id: str = None, request: Request = None):
    """sessions.usage：获取单个会话用量"""
    try:
        result = await _forward_rpc(
            request=request,
            method="sessions.usage",
            device_id=device_id,
            params={"key": session_key},
            timeout=10.0,
        )
        if not result.get("success"):
            return result
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        return {"success": True, "usage": data}
    except Exception as e:
        logger.error("[sessions.usage] %s", e)
        return {"success": False, "error": str(e)}
