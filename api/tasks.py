"""
Tasks/Cron 管理 API - 调用设备端 Gateway RPC
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.supabase import get_db

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_tasks(device_id: str = None, request: Request = None):
    """获取任务列表 - 从设备端 Gateway cron.list 获取"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required", "jobs": [], "count": 0}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "cron.list", {}, method="GET", timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Failed to get tasks: {result}")
            return {"success": False, "error": result.get("error"), "jobs": [], "count": 0}
        
        jobs = result.get("jobs", []) if isinstance(result, dict) else []
        
        return {
            "success": True,
            "jobs": jobs,
            "count": len(jobs),
            "total": result.get("total", len(jobs))
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "jobs": [], "count": 0}


@router.post("")
async def create_task(
    device_id: str = None,
    request: Request = None,
    name: str = None,
    schedule: str = None,
    message: str = None,
    enabled: bool = True
):
    """创建任务"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    if not name or not schedule:
        return {"success": False, "error": "name and schedule are required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        params = {
            "name": name,
            "schedule": schedule,
        }
        if message:
            params["message"] = message
            
        result = await manager.send_request(device_id, "cron.add", params, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {
            "success": True,
            "jobId": result.get("jobId", str(uuid.uuid4())[:8]),
            "message": "Task created"
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.patch("/{job_id}")
async def update_task(
    job_id: str,
    device_id: str = None,
    request: Request = None,
    name: str = None,
    schedule: str = None,
    enabled: bool = None
):
    """更新任务"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    if not name and not schedule and enabled is None:
        return {"success": False, "error": "No fields to update"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        params = {"jobId": job_id}
        if name:
            params["name"] = name
        if schedule:
            params["schedule"] = schedule
        if enabled is not None:
            params["enabled"] = enabled
            
        result = await manager.send_request(device_id, "cron.edit", params, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Task updated"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/{job_id}")
async def delete_task(job_id: str, device_id: str = None, request: Request = None):
    """删除任务"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "cron.delete", {"jobId": job_id}, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Task deleted"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.post("/{job_id}/run")
async def run_task(job_id: str, device_id: str = None, request: Request = None):
    """立即执行任务"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "cron.run", {"jobId": job_id}, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Task executed"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}
