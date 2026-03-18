"""Sessions 管理 API（通过设备代理调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
from typing import Optional

from app.core.websocket import manager
from app.core.supabase import get_db
from api.proxy import _require_user_device

router = APIRouter(prefix="/devices", tags=["会话管理"])


@router.get("/{device_id}/agents")
async def list_agents(device_id: str, request: Request):
    """获取设备上的 Agent 列表（agents.list RPC）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "agents.list", {}, timeout=15.0)
        payload = result.get("data") or {}
        agents = payload.get("agents") or []
        # 若设备返回空，至少给出默认 main agent
        if not agents:
            agents = [{"id": "main", "name": "main", "isDefault": True}]
        return {"success": True, "agents": agents}
    except HTTPException:
        raise
    except Exception as e:
        # agents.list 失败时降级返回默认 agent，不影响正常聊天
        return {"success": True, "agents": [{"id": "main", "name": "main", "isDefault": True}]}


@router.get("/{device_id}/sessions")
async def list_sessions(
    device_id: str,
    request: Request,
    agentId: Optional[str] = Query(default=None),
):
    """获取会话列表（sessions.list RPC），可按 agentId 过滤"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    params: dict = {}
    if agentId:
        params["agentId"] = agentId
    try:
        result = await manager.send_request(device_id, "sessions.list", params)
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
    name: Optional[str] = None
    label: Optional[str] = None
    pinned: Optional[bool] = None
    model: Optional[str] = None


@router.patch("/{device_id}/sessions/{session_key}")
async def patch_session(device_id: str, session_key: str, body: SessionPatchRequest, request: Request):
    """重命名 / pin 会话"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if "label" in patch and "name" not in patch:
        patch["name"] = patch.pop("label")
    else:
        patch.pop("label", None)
    if not patch:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    try:
        result = await manager.send_request(
            device_id,
            "sessions.patch",
            {"key": session_key, "sessionKey": session_key, "patch": patch},
        )
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


# ── chat.history ────────────────────────────────────────────────────────────

@router.get("/{device_id}/chat/history")
async def get_chat_history(
    device_id: str,
    request: Request,
    sessionKey: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """通过 Gateway WS 获取会话历史（chat.history RPC）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    params: dict = {"limit": limit}
    if sessionKey:
        params["sessionKey"] = sessionKey
    try:
        result = await manager.send_request(device_id, "chat.history", params)
        payload = result.get("data") or {}
        return {"success": True, "messages": payload.get("messages", []), "sessionKey": payload.get("sessionKey")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── chat.abort ──────────────────────────────────────────────────────────────

class AbortRequest(BaseModel):
    sessionKey: Optional[str] = None
    runId: Optional[str] = None


@router.post("/{device_id}/chat/abort")
async def abort_chat(device_id: str, body: AbortRequest, request: Request):
    """通过 Gateway WS 中止正在执行的任务（chat.abort RPC）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    params: dict = {}
    if body.sessionKey:
        params["sessionKey"] = body.sessionKey
    if body.runId:
        params["runId"] = body.runId
    try:
        result = await manager.send_request(device_id, "chat.abort", params, timeout=10.0)
        payload = result.get("data") or {}
        return {"success": True, "aborted": payload.get("aborted", True)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
