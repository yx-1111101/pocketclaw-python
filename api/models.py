"""模型列表 API（通过设备代理调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException, Request

from app.core.websocket import manager
from app.core.supabase import get_db
from api.proxy import _require_user_device

router = APIRouter(prefix="/devices", tags=["模型"])


@router.get("/{device_id}/models")
async def list_models(device_id: str, request: Request):
    """获取可用模型列表（Gateway WS: models.list）"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "models.list", {"includeAll": True})
        payload = result.get("data") or {}
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            payload = payload.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
            payload = payload.get("result")
        if isinstance(payload, dict) and payload.get("ok") is False:
            raise HTTPException(status_code=502, detail=f"models.list failed: {payload.get('error')}")
        return {"success": True, "models": payload.get("models", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
