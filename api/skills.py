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
device_router = APIRouter(prefix="/devices", tags=["设备-技能"])

logger = logging.getLogger(__name__)


def _rpc_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 manager.send_request 的返回结构：{status, request_id, data}"""
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _derive_skill_status(skill: Dict[str, Any]) -> str:
    raw = skill.get("status")
    if isinstance(raw, str) and raw:
        return raw
    if bool(skill.get("disabled")):
        return "disabled"
    if bool(skill.get("blockedByAllowlist")):
        return "blocked"
    missing = skill.get("missing")
    if isinstance(missing, list) and missing:
        return "missing"
    if bool(skill.get("eligible")):
        return "ready"
    return "missing"


def _normalize_skill(skill: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(skill or {})
    skill_key = str(item.get("skillKey") or item.get("id") or item.get("name") or "").strip()
    if skill_key and "id" not in item:
        item["id"] = skill_key
    if skill_key and "skillKey" not in item:
        item["skillKey"] = skill_key
    if skill_key and "name" not in item:
        item["name"] = skill_key
    item["status"] = _derive_skill_status(item)
    item["enabled"] = not bool(item.get("disabled"))
    return item


def _is_skill_ready(skill: Dict[str, Any]) -> bool:
    return str(skill.get("status") or "").lower() in ("ready", "enabled")


def _skill_source_group(skill: Dict[str, Any]) -> str:
    source = str(skill.get("source") or "").lower()
    if "bundled" in source:
        return "bundled"
    if "extra" in source:
        return "extra"
    return "workspace"


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
        result = await manager.send_request(device_id, "skills.status", {}, method="GET", timeout=15.0)
        payload = _rpc_payload(result)
        raw_skills = payload.get("skills", []) if isinstance(payload, dict) else []
        skills: List[Dict[str, Any]] = [
            _normalize_skill(s) for s in raw_skills if isinstance(s, dict)
        ]
        
        # 按来源分类
        categorized = {
            "bundled": [],    # 系统内置
            "extra": [],      # 官方扩展
            "workspace": [],   # 用户自装
        }
        
        for skill in skills:
            # 过滤不可用
            if filter_unavailable and not _is_skill_ready(skill):
                continue
            
            # 分类
            group = _skill_source_group(skill)
            categorized[group].append(skill)
        
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
            "readyCount": sum(1 for s in skills if isinstance(skills, list) and _is_skill_ready(s)) if isinstance(skills, list) else 0,
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
        result = await manager.send_request(device_id, "skills.status", {}, method="GET", timeout=15.0)
        payload = _rpc_payload(result)
        raw_skills = payload.get("skills", []) if isinstance(payload, dict) else []
        skills: List[Dict[str, Any]] = [
            _normalize_skill(s) for s in raw_skills if isinstance(s, dict)
        ]
        
        total = len(skills)
        ready = sum(1 for s in skills if _is_skill_ready(s))
        missing = sum(1 for s in skills if s.get("status") == "missing")
        disabled = sum(1 for s in skills if s.get("status") == "disabled")
        blocked = sum(1 for s in skills if s.get("status") == "blocked")
        
        # 按分类统计
        bundled = [s["id"] for s in skills if _skill_source_group(s) == "bundled"]
        extra = [s["id"] for s in skills if _skill_source_group(s) == "extra"]
        workspace = [s["id"] for s in skills if _skill_source_group(s) == "workspace"]
        
        return {
            "success": True,
            "total": total,
            "readyCount": ready,
            "missingCount": missing,
            "disabledCount": disabled,
            "blockedCount": blocked,
            "readySkills": [s["id"] for s in skills if _is_skill_ready(s)],
            "categories": {
                "bundled": {"total": len(bundled), "ready": sum(1 for s in skills if _skill_source_group(s) == "bundled" and _is_skill_ready(s))},
                "extra": {"total": len(extra), "ready": sum(1 for s in skills if _skill_source_group(s) == "extra" and _is_skill_ready(s))},
                "workspace": {"total": len(workspace), "ready": sum(1 for s in skills if _skill_source_group(s) == "workspace" and _is_skill_ready(s))}
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
        result = await manager.send_request(
            device_id,
            "skills.update",
            {"skillKey": skill_id, "enabled": True},
            timeout=10.0,
        )
        payload = _rpc_payload(result)
        if isinstance(payload, dict) and payload.get("ok") is False:
            return {"success": False, "error": payload}
        
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
        result = await manager.send_request(
            device_id,
            "skills.update",
            {"skillKey": skill_id, "enabled": False},
            timeout=10.0,
        )
        payload = _rpc_payload(result)
        if isinstance(payload, dict) and payload.get("ok") is False:
            return {"success": False, "error": payload}
        
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
        result = await manager.send_request(device_id, "skills.status", {}, method="GET", timeout=15.0)
        payload = _rpc_payload(result)
        raw_skills = payload.get("skills", []) if isinstance(payload, dict) else []
        skills: List[Dict[str, Any]] = [
            _normalize_skill(s) for s in raw_skills if isinstance(s, dict)
        ]
        skill = next(
            (
                s for s in skills
                if s.get("id") == skill_id or s.get("skillKey") == skill_id or s.get("name") == skill_id
            ),
            None,
        )
        
        if not skill:
            return {"success": False, "error": "Skill not found"}
        
        return {"success": True, "skill": skill}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}



async def install_skill(device_id: str = None, request: Request = None, name: str = None, version: str = None):
    """安装技能"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    if not name:
        return {"success": False, "error": "name required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        params = {"skillId": name}
        if version:
            params["version"] = version
            
        result = await manager.send_request(device_id, "skills.install", params, timeout=30.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Skill installed"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


async def uninstall_skill(skill_id: str, device_id: str = None, request: Request = None):
    """卸载技能"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "skills.uninstall", {"skillId": skill_id}, timeout=10.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "message": "Skill uninstalled"}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}

# ========== 设备前缀路由 (小程序调用) ==========

@device_router.get("/{device_id}/skills")
async def device_list_skills(device_id: str, request: Request):
    """获取技能列表 - 设备前缀 (小程序调用)"""
    # 直接调用 skills.list
    return await list_skills(device_id=device_id, request=request)


@device_router.post("/{device_id}/skills/install")
async def device_install_skill(device_id: str, request: Request):
    """安装技能"""
    return await install_skill(device_id=device_id, request=request)


@device_router.delete("/{device_id}/skills/{skill_id}")
async def device_uninstall_skill(device_id: str, skill_id: str, request: Request):
    """卸载技能"""
    return await uninstall_skill(skill_id=skill_id, device_id=device_id, request=request)


@device_router.get("/{device_id}/skills/{skill_id}")
async def device_get_skill(skill_id: str, device_id: str, request: Request):
    """获取技能详情"""
    return await get_skill(skill_id=skill_id, device_id=device_id, request=request)
