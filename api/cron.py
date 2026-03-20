"""Cron 任务管理 API（通过设备代理调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Any

from app.core.websocket import manager
from app.core.supabase import get_db
from api.proxy import _require_user_device

router = APIRouter(prefix="/devices", tags=["定时任务"])


@router.get("/{device_id}/cron")
async def list_cron(device_id: str, request: Request):
    """获取所有 cron 任务"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    
    # 检查设备是否在线
    if not manager.is_connected(device_id):
        return {
            "success": True,
            "jobs": [],
            "offline": True,
            "message": "设备离线"
        }
    
    try:
        result = await manager.send_request(device_id, "cron.list", {})
        payload = result.get("data") or {}
        return {"success": True, "jobs": payload.get("jobs", []), "offline": False}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CronAddRequest(BaseModel):
    name: Optional[str] = None
    schedule: dict          # {"kind": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"}
    payload: dict           # {"kind": "agentTurn", "message": "..."}
    session_target: str = "isolated"   # "main" | "isolated"
    enabled: bool = True
    delivery: Optional[dict] = None


@router.post("/{device_id}/cron")
async def add_cron(device_id: str, body: CronAddRequest, request: Request):
    """创建 cron 任务"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    job = {
        "schedule": body.schedule,
        "payload": body.payload,
        "sessionTarget": body.session_target,
        "enabled": body.enabled,
    }
    if body.name:
        job["name"] = body.name
    if body.delivery:
        job["delivery"] = body.delivery
    try:
        result = await manager.send_request(device_id, "cron.add", {"job": job})
        payload = result.get("data") or {}
        return {"success": True, "job": payload.get("job", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CronPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None
    schedule: Optional[dict] = None
    payload: Optional[dict] = None


@router.patch("/{device_id}/cron/{job_id}")
async def update_cron(device_id: str, job_id: str, body: CronPatchRequest, request: Request):
    """更新 cron 任务"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    try:
        result = await manager.send_request(device_id, "cron.update", {"jobId": job_id, "patch": patch})
        payload = result.get("data") or {}
        return {"success": True, "job": payload.get("job", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{device_id}/cron/{job_id}")
async def delete_cron(device_id: str, job_id: str, request: Request):
    """删除 cron 任务"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        await manager.send_request(device_id, "cron.remove", {"jobId": job_id})
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{device_id}/cron/{job_id}/run")
async def run_cron(device_id: str, job_id: str, request: Request):
    """立即执行 cron 任务"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "cron.run", {"jobId": job_id})
        payload = result.get("data") or {}
        return {"success": True, "result": payload}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{device_id}/cron/{job_id}/runs")
async def cron_runs(device_id: str, job_id: str, request: Request):
    """获取 cron 任务运行历史"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "cron.runs", {"jobId": job_id})
        payload = result.get("data") or {}
        return {"success": True, "runs": payload.get("runs", [])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
