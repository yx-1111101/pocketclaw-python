"""
Tasks/Cron 管理 API - 调用真实 Gateway RPC
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import logging

from app.core.gateway_rpc import call_gateway_rpc_sync

router = APIRouter(prefix="/tasks", tags=["tasks"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_tasks():
    """获取任务列表 - 从 Gateway cron.list 获取"""
    try:
        result = call_gateway_rpc_sync("cron.list", timeout=10.0)
        
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
    name: str = None,
    schedule: str = None,
    message: str = None,
    enabled: bool = True
):
    """创建任务"""
    if not name or not schedule:
        return {"success": False, "error": "name and schedule are required"}
    
    try:
        params = {
            "name": name,
            "schedule": schedule,
        }
        if message:
            params["message"] = message
            
        result = call_gateway_rpc_sync("cron.add", params)
        
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
    name: str = None,
    schedule: str = None,
    enabled: bool = None
):
    """更新任务"""
    if not name and not schedule and enabled is None:
        return {"success": False, "error": "No fields to update"}
    
    try:
        params = {"jobId": job_id}
        if name:
            params["name"] = name
        if schedule:
            params["schedule"] = schedule
        if enabled is not None:
            params["enabled"] = enabled
            
        result = call_gateway_rpc_sync("cron.edit", params)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Task updated"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/{job_id}")
async def delete_task(job_id: str):
    """删除任务"""
    try:
        result = call_gateway_rpc_sync("cron.delete", {"jobId": job_id})
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Task deleted"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.post("/{job_id}/run")
async def run_task(job_id: str):
    """立即执行任务"""
    try:
        result = call_gateway_rpc_sync("cron.run", {"jobId": job_id})
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Task executed"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}
