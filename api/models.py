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
        result = await manager.send_request(device_id, "models.list", {})
        payload = result.get("data") or {}
        return {"success": True, "models": payload.get("models", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
