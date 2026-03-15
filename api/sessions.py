"""Sessions 管理 API（调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.gateway_client import gateway_request

router = APIRouter(prefix="/system/sessions", tags=["会话管理"])


@router.get("")
async def list_sessions():
    """获取所有会话列表"""
    try:
        payload = await gateway_request("sessions.list", {})
        sessions = payload.get("sessions", [])
        return {"success": True, "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_key}/usage")
async def session_usage(session_key: str):
    """获取会话用量统计"""
    try:
        payload = await gateway_request("sessions.usage", {"sessionKey": session_key})
        return {"success": True, "usage": payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SessionPatchRequest(BaseModel):
    label: Optional[str] = None
    pinned: Optional[bool] = None


@router.patch("/{session_key}")
async def patch_session(session_key: str, body: SessionPatchRequest):
    """重命名 / pin 会话"""
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    try:
        payload = await gateway_request("sessions.patch", {"sessionKey": session_key, "patch": patch})
        return {"success": True, "session": payload.get("session", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_key}")
async def delete_session(session_key: str):
    """删除会话"""
    try:
        await gateway_request("sessions.delete", {"sessionKey": session_key})
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
