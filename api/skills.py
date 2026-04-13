"""
Skills 管理 API - 调用设备端 Gateway RPC
"""
from fastapi import APIRouter, Request
from typing import Optional, Dict, Any, List
from enum import Enum
import logging

from api._gateway import norm_text as _norm_text
from api._gateway import read_json_body as _read_json_body
from api._gateway import resolve_device_id as _resolve_device_id
from api._gateway import rpc_payload as _rpc_payload
from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.db import get_db

router = APIRouter(prefix="/skills", tags=["skills"])

logger = logging.getLogger(__name__)


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


def _should_hide_skill(skill: Dict[str, Any]) -> bool:
    """
    对小程序隐藏当前不可用的技能：
    - always 保留（系统常驻）
    - 非 always 且 eligible=False 的统一不下发（包含“受限启用”和“不可用未启用”）
    """
    if bool(skill.get("always")):
        return False
    return not bool(skill.get("eligible"))


def _skill_source_group(skill: Dict[str, Any]) -> str:
    source = str(skill.get("source") or "").lower()
    if "bundled" in source:
        return "bundled"
    if "extra" in source:
        return "extra"
    return "workspace"

def _extract_search_items(payload: Dict[str, Any]) -> List[Any]:
    if not isinstance(payload, dict):
        return []
    for key in ("items", "skills", "results"):
        items = payload.get(key)
        if isinstance(items, list):
            return items
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("items", "skills", "results"):
            items = data.get(key)
            if isinstance(items, list):
                return items
    return []


def _normalize_search_item(item: Any) -> Optional[Dict[str, str]]:
    if isinstance(item, str):
        slug = _norm_text(item)
        if not slug:
            return None
        return {
            "slug": slug,
            "name": slug,
            "version": "",
            "description": "",
            "homepage": "",
        }

    if not isinstance(item, dict):
        return None

    slug = _norm_text(
        item.get("slug")
        or item.get("name")
        or item.get("id")
        or item.get("skill")
        or item.get("package")
    )
    if not slug:
        return None

    name = _norm_text(item.get("title") or item.get("displayName") or item.get("label") or slug)
    version = _norm_text(item.get("latestVersion") or item.get("version") or item.get("tag"))
    description = _norm_text(item.get("description") or item.get("summary"))
    homepage = _norm_text(item.get("homepage") or item.get("url"))

    return {
        "slug": slug,
        "name": name,
        "version": version,
        "description": description,
        "homepage": homepage,
    }

async def _load_status_skills(device_id: str) -> List[Dict[str, Any]]:
    result = await manager.send_request(device_id, "skills.status", {}, method="GET", timeout=15.0)
    payload = _rpc_payload(result)
    raw_skills = payload.get("skills", []) if isinstance(payload, dict) else []
    return [_normalize_skill(s) for s in raw_skills if isinstance(s, dict)]


async def _resolve_and_auth_device(
    request: Request,
    device_id: Optional[str] = None,
    body: Dict[str, Any] = None,
) -> str:
    did = await _resolve_device_id(device_id, request, body)
    if not did:
        return ""
    db = get_db()
    await _require_user_device(db, request, did)
    return did


async def _set_skill_enabled(
    skill_id: str,
    enabled: bool,
    request: Request,
    device_id: Optional[str] = None,
    body: Dict[str, Any] = None,
):
    if not request:
        return {"success": False, "error": "device_id required"}
    did = await _resolve_and_auth_device(request=request, device_id=device_id, body=body)
    if not did:
        return {"success": False, "error": "device_id required"}

    result = await manager.send_request(
        did,
        "skills.update",
        {"skillKey": skill_id, "enabled": bool(enabled)},
        timeout=10.0,
    )
    payload = _rpc_payload(result)
    if isinstance(payload, dict) and payload.get("ok") is False:
        return {"success": False, "error": payload}
    return {"success": True, "enabled": bool(enabled)}


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
    filter_unavailable: bool = False
):
    """获取技能列表 - 从设备端 Gateway 获取
    
    Args:
        device_id: 设备ID
        category: 过滤分类 (bundled/extra/workspace/all)
        filter_unavailable: 是否过滤掉不可用的技能 (默认false)
    """
    if not request:
        return {"success": False, "error": "device_id required", "skills": [], "count": 0}
    
    try:
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id)
        if not device_id:
            return {"success": False, "error": "device_id required", "skills": [], "count": 0}
        skills = await _load_status_skills(device_id)
        # # 默认返回完整技能集合；仅在显式开启时过滤不可用技能。
        # if filter_unavailable:
        #     skills = [s for s in skills if not _should_hide_skill(s)]

        # 按来源分类
        categorized = {
            "bundled": [],    # 系统内置
            "extra": [],      # 官方扩展
            "workspace": [],   # 用户自装
        }
        
        for skill in skills:
            # 过滤“真正不可用”的技能：missing / blocked
            # 注意 disabled 表示用户主动关闭，应保留并展示为“未启用”
            status = str(skill.get("status") or "").lower()
            if filter_unavailable and status in ("missing", "blocked"):
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
async def check_skills(device_id: str = None, request: Request = None, filter_unavailable: bool = False):
    """技能状态检查 - 从设备端 Gateway 获取"""
    if not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id)
        if not device_id:
            return {"success": False, "error": "device_id required"}
        skills = await _load_status_skills(device_id)
        if filter_unavailable:
            skills = [s for s in skills if not _should_hide_skill(s)]
        
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
    try:
        return await _set_skill_enabled(
            skill_id=skill_id,
            enabled=True,
            request=request,
            device_id=device_id,
        )
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.post("/{skill_id}/disable")
async def disable_skill(skill_id: str, device_id: str = None, request: Request = None):
    """禁用技能"""
    try:
        return await _set_skill_enabled(
            skill_id=skill_id,
            enabled=False,
            request=request,
            device_id=device_id,
        )
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.patch("/{skill_id}")
async def patch_skill(skill_id: str, device_id: str = None, request: Request = None):
    """更新技能状态（当前仅支持 enabled）"""
    if not request:
        return {"success": False, "error": "device_id required"}
    try:
        body = await _read_json_body(request)
        if "enabled" not in body:
            return {"success": False, "error": "enabled required"}
        enabled = bool(body.get("enabled"))
        return await _set_skill_enabled(
            skill_id=skill_id,
            enabled=enabled,
            request=request,
            device_id=device_id,
            body=body,
        )
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/search")
async def search_skills(
    device_id: str = None,
    request: Request = None,
    q: str = "",
    limit: int = 10,
):
    """搜索可安装技能（走设备 file-server 的 /skills/search）"""
    if not request:
        return {"success": False, "error": "device_id required", "items": [], "count": 0}

    keyword = _norm_text(q)
    if not keyword:
        return {"success": True, "items": [], "count": 0, "query": keyword}

    safe_limit = max(1, min(int(limit or 10), 30))

    try:
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id)
        if not device_id:
            return {"success": False, "error": "device_id required", "items": [], "count": 0}

        result = await manager.send_request(
            device_id,
            "skills/search",
            {},
            method="GET",
            query={"q": keyword, "limit": safe_limit},
            timeout=25.0,
        )
        payload = _rpc_payload(result)

        if isinstance(payload, dict) and payload.get("success") is False:
            return payload
        if isinstance(payload, dict) and payload.get("error"):
            return {"success": False, "error": payload.get("error"), "items": [], "count": 0}

        raw_items = _extract_search_items(payload)
        items = [x for x in (_normalize_search_item(it) for it in raw_items) if x]
        return {
            "success": True,
            "items": items,
            "count": len(items),
            "query": keyword,
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "items": [], "count": 0}


@router.get("/market")
async def get_skill_market(
    device_id: str = None,
    request: Request = None,
    category: str = "",
    q: str = "",
):
    """获取技能市场列表 - 从设备 file-server 获取"""
    if not request:
        return {"success": False, "error": "device_id required", "skills": [], "featured": None}
    
    try:
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id)
        if not device_id:
            return {"success": False, "error": "device_id required", "skills": [], "featured": None}
        
        params: Dict[str, Any] = {}
        if category:
            params["category"] = category
        if q:
            params["q"] = q
        
        result = await manager.send_request(
            device_id,
            "api/skills/market",
            {},
            method="GET",
            query=params,
            timeout=15.0,
        )
        payload = _rpc_payload(result)
        
        if isinstance(payload, dict) and payload.get("success") is False:
            return payload
        if isinstance(payload, dict) and payload.get("error"):
            return {"success": False, "error": payload.get("error"), "skills": [], "featured": None}
        
        return {
            "success": True,
            "skills": payload.get("skills", []),
            "featured": payload.get("featured"),
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "skills": [], "featured": None}


@router.get("/{skill_id}")
async def get_skill(skill_id: str, device_id: str = None, request: Request = None):
    """获取技能详情"""
    if not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id)
        if not device_id:
            return {"success": False, "error": "device_id required"}
        skills = await _load_status_skills(device_id)
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


@router.post("/install")
async def install_skill(device_id: str = None, request: Request = None):
    """安装新技能（走设备 file-server 的 /skills/install，底层由 ClawHub 处理）"""
    if not request:
        return {"success": False, "error": "device_id required"}

    try:
        body = await _read_json_body(request)
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id, body=body)
        if not device_id:
            return {"success": False, "error": "device_id required"}
        skill_name = _norm_text(body.get("name"))
        if not skill_name:
            return {"success": False, "error": "name required"}

        version = _norm_text(body.get("version"))

        params: Dict[str, Any] = {"name": skill_name}
        if version:
            params["version"] = version

        result = await manager.send_request(device_id, "skills/install", params, method="POST", timeout=120.0)
        payload = _rpc_payload(result)

        if isinstance(payload, dict) and payload.get("success") is False:
            return payload
        if isinstance(payload, dict) and payload.get("error"):
            return {"success": False, "error": payload.get("error"), "result": payload}
        if isinstance(payload, dict) and payload.get("success") is True:
            return payload

        return {
            "success": True,
            "message": "Skill install requested",
            "name": skill_name,
            "version": version or "latest",
            "result": payload,
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.delete("/{skill_id}")
async def uninstall_skill(skill_id: str, device_id: str = None, request: Request = None):
    """当前网关不提供卸载 RPC，保留路由仅返回明确错误。"""
    if not request:
        return {"success": False, "error": "device_id required"}
    try:
        device_id = await _resolve_and_auth_device(request=request, device_id=device_id)
        if not device_id:
            return {"success": False, "error": "device_id required"}
        return {
            "success": False,
            "error": "uninstall_not_supported",
            "message": "当前网关不支持 skills.uninstall，请使用禁用功能代替卸载",
            "skillId": skill_id,
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}
