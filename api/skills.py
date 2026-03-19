"""
Skills 管理 API - 调用真实 Gateway RPC
"""
from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any
import logging

from app.core.gateway_rpc import call_gateway_rpc_sync

router = APIRouter(prefix="/skills", tags=["skills"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_skills():
    """获取技能列表 - 从 Gateway 获取"""
    try:
        result = call_gateway_rpc_sync("skills.list", timeout=15.0)
        
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
async def check_skills():
    """技能状态检查 - 从 Gateway 获取"""
    try:
        # skills.list 已经包含状态信息
        result = call_gateway_rpc_sync("skills.list", timeout=15.0)
        
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
async def enable_skill(skill_id: str):
    """启用技能"""
    try:
        result = call_gateway_rpc_sync("skills.enable", {"skillId": skill_id})
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "enabled": True}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.post("/{skill_id}/disable")
async def disable_skill(skill_id: str):
    """禁用技能"""
    try:
        result = call_gateway_rpc_sync("skills.disable", {"skillId": skill_id})
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "enabled": False}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/{skill_id}")
async def get_skill(skill_id: str):
    """获取技能详情"""
    try:
        result = call_gateway_rpc_sync("skills.list", timeout=15.0)
        
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
