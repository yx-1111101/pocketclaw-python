"""
Skills 管理 API - 调用设备端 Gateway RPC
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any, List
from enum import Enum
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.supabase import get_db

router = APIRouter(prefix="/skills", tags=["skills"])
logger = logging.getLogger(__name__)


class SkillCategory(str, Enum):
    """技能分类"""
    BUNDLED = "bundled"       # 系统内置
    EXTRA = "extra"           # 官方扩展
    WORKSPACE = "workspace"   # 用户自装
    ALL = "all"


@router.get("")
async def list_skills(
    device_id: str = None, 
    request: Request = None,
    category: SkillCategory = SkillCategory.ALL,
    filter_unavailable: bool = True
):
    """获取技能列表 - 从设备端 Gateway 获取
    
    Args:
        device_id: 设备ID
        category: 过滤分类 (bundled/extra/workspace/all)
        filter_unavailable: 是否过滤掉不可用的技能 (默认true)
    """
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
        
        # 按来源分类
        categorized = {
            "bundled": [],    # 系统内置
            "extra": [],      # 官方扩展
            "workspace": [],   # 用户自装
        }
        
        for skill in skills:
            source = skill.get("source", "")
            status = skill.get("status", "missing")
            
            # 过滤不可用
            if filter_unavailable and status not in ("ready", "enabled"):
                continue
            
            # 分类
            if "bundled" in source:
                categorized["bundled"].append(skill)
            elif "extra" in source:
                categorized["extra"].append(skill)
            elif "workspace" in source:
                categorized["workspace"].append(skill)
        
        # 根据 category 过滤
        if category != SkillCategory.ALL:
            skills = categorized.get(category, [])
        else:
            # 返回所有分类
            skills = {
                "bundled": categorized["bundled"],
                "extra": categorized["extra"], 
                "workspace": categorized["workspace"],
                "all_count": len(categorized["bundled"]) + len(categorized["extra"]) + len(categorized["workspace"])
            }
        
        return {
            "success": True, 
            "skills": skills, 
            "count": len(skills) if isinstance(skills, list) else skills.get("all_count", 0),
            "readyCount": sum(1 for s in skills if isinstance(skills, list) and s.get("status") == "ready") if isinstance(skills, list) else 0,
            "categories": {
                "bundled": len(categorized["bundled"]),
                "extra": len(categorized["extra"]),
                "workspace": len(categorized["workspace"])
            } if category == SkillCategory.ALL else None
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
        
        # 按分类统计
        bundled = [s["id"] for s in skills if "bundled" in s.get("source", "")]
        extra = [s["id"] for s in skills if "extra" in s.get("source", "")]
        workspace = [s["id"] for s in skills if "workspace" in s.get("source", "")]
        
        return {
            "success": True,
            "total": total,
            "readyCount": ready,
            "missingCount": missing,
            "disabledCount": disabled,
            "readySkills": [s["id"] for s in skills if s.get("status") == "ready"],
            "categories": {
                "bundled": {"total": len(bundled), "ready": sum(1 for s in skills if "bundled" in s.get("source", "") and s.get("status") == "ready")},
                "extra": {"total": len(extra), "ready": sum(1 for s in skills if "extra" in s.get("source", "") and s.get("status") == "ready")},
                "workspace": {"total": len(workspace), "ready": sum(1 for s in skills if "workspace" in s.get("source", "") and s.get("status") == "ready")}
            }
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
