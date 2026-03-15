"""Sessions 管理 API（通过设备代理调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from app.core.websocket import manager
from app.core.supabase import get_db
from api.proxy import _require_user_device

router = APIRouter(prefix="/devices", tags=["会话管理"])


@router.get("/{device_id}/sessions")
async def list_sessions(device_id: str, request: Request):
    """获取所有会话列表"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "sessions.list", {})
        payload = result.get("data") or {}
        return {"success": True, "sessions": payload.get("sessions", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}/sessions/{session_key}/usage")
async def session_usage(device_id: str, session_key: str, request: Request):
    """获取会话用量统计"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "sessions.usage", {"sessionKey": session_key})
        payload = result.get("data") or {}
        return {"success": True, "usage": payload}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SessionPatchRequest(BaseModel):
    label: Optional[str] = None
    pinned: Optional[bool] = None


@router.patch("/{device_id}/sessions/{session_key}")
async def patch_session(device_id: str, session_key: str, body: SessionPatchRequest, request: Request):
    """重命名 / pin 会话"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    try:
        result = await manager.send_request(device_id, "sessions.patch", {"sessionKey": session_key, "patch": patch})
        payload = result.get("data") or {}
        return {"success": True, "session": payload.get("session", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}/sessions/{session_key}")
async def delete_session(device_id: str, session_key: str, request: Request):
    """删除会话"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        await manager.send_request(device_id, "sessions.delete", {"sessionKey": session_key})
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
