"""
Skills 管理 API - 调用设备端 Gateway RPC
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.supabase import get_db

router = APIRouter(prefix="/skills", tags=["skills"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_skills(device_id: str = None, request: Request = None):
    """获取技能列表 - 从设备端 Gateway 获取"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required", "skills": [], "count": 0}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "skills.list", {}, method="GET", timeout=15.0)
        
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Failed to get skills: {result}")
            return {"success": False, "error": result.get("error"), "skills": [], "count": 0}
        
        skills = result.get("skills", []) if isinstance(result, dict) else []
        
        return {
            "success": True, 
            "skills": skills, 
            "count": len(skills),
            "readyCount": sum(1 for s in skills if s.get("status") == "ready")
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "skills": [], "count": 0}


@router.get("/check")
async def check_skills(device_id: str = None, request: Request = None):
    """技能状态检查 - 从设备端 Gateway 获取"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "skills.list", {}, method="GET", timeout=15.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        skills = result.get("skills", []) if isinstance(result, dict) else []
        
        total = len(skills)
        ready = sum(1 for s in skills if s.get("status") == "ready")
        missing = sum(1 for s in skills if s.get("status") == "missing")
        disabled = sum(1 for s in skills if s.get("status") == "disabled")
        
        return {
            "success": True,
            "total": total,
            "readyCount": ready,
            "missingCount": missing,
            "disabledCount": disabled,
            "readySkills": [s["id"] for s in skills if s.get("status") == "ready"]
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.post("/{skill_id}/enable")
async def enable_skill(skill_id: str, device_id: str = None, request: Request = None):
    """启用技能"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "skills.enable", {"skillId": skill_id}, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "enabled": True}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.post("/{skill_id}/disable")
async def disable_skill(skill_id: str, device_id: str = None, request: Request = None):
    """禁用技能"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "skills.disable", {"skillId": skill_id}, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "enabled": False}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/{skill_id}")
async def get_skill(skill_id: str, device_id: str = None, request: Request = None):
    """获取技能详情"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "skills.list", {}, method="GET", timeout=15.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        skills = result.get("skills", []) if isinstance(result, dict) else []
        skill = next((s for s in skills if s.get("id") == skill_id), None)
        
        if not skill:
            return {"success": False, "error": "Skill not found"}
        
        return {"success": True, "skill": skill}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}
