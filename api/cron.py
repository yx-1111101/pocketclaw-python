"""Cron 任务管理 API（调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Any
from app.core.gateway_client import gateway_request

router = APIRouter(prefix="/system/cron", tags=["定时任务"])


@router.get("")
async def list_cron():
    """获取所有 cron 任务"""
    try:
        payload = await gateway_request("cron.list", {})
        return {"success": True, "jobs": payload.get("jobs", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CronAddRequest(BaseModel):
    name: Optional[str] = None
    schedule: dict          # {"kind": "cron", "expr": "0 9 * * *", "tz": "Asia/Shanghai"}
    payload: dict           # {"kind": "agentTurn", "message": "..."}
    session_target: str = "isolated"   # "main" | "isolated"
    enabled: bool = True
    delivery: Optional[dict] = None


@router.post("")
async def add_cron(body: CronAddRequest):
    """创建 cron 任务"""
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
        payload = await gateway_request("cron.add", {"job": job})
        return {"success": True, "job": payload.get("job", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CronPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = None
    schedule: Optional[dict] = None
    payload: Optional[dict] = None


@router.patch("/{job_id}")
async def update_cron(job_id: str, body: CronPatchRequest):
    """更新 cron 任务"""
    patch = {k: v for k, v in body.dict().items() if v is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="没有要更新的字段")
    try:
        payload = await gateway_request("cron.update", {"jobId": job_id, "patch": patch})
        return {"success": True, "job": payload.get("job", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{job_id}")
async def delete_cron(job_id: str):
    """删除 cron 任务"""
    try:
        await gateway_request("cron.remove", {"jobId": job_id})
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{job_id}/run")
async def run_cron(job_id: str):
    """立即执行 cron 任务"""
    try:
        payload = await gateway_request("cron.run", {"jobId": job_id})
        return {"success": True, "result": payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{job_id}/runs")
async def cron_runs(job_id: str):
    """获取 cron 任务运行历史"""
    try:
        payload = await gateway_request("cron.runs", {"jobId": job_id})
        return {"success": True, "runs": payload.get("runs", [])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
