"""Skills 管理 API（通过设备代理调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

from app.core.websocket import manager
from app.core.supabase import get_db
from api.proxy import _require_user_device

router = APIRouter(prefix="/devices", tags=["技能管理"])


@router.get("/{device_id}/skills")
async def list_skills(device_id: str, request: Request):
    """获取所有技能列表"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "skills.status", {})
        payload = result.get("data") or {}
        skills = payload.get("skills", [])
        return {
            "success": True,
            "skills": [
                {
                    "name": s.get("name"),
                    "description": s.get("description", "").split("\n")[0],
                    "enabled": not s.get("disabled", False),
                    "eligible": s.get("eligible", True),
                    "source": s.get("source", ""),
                    "always": s.get("always", False),
                }
                for s in skills
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SkillUpdateRequest(BaseModel):
    enabled: bool


@router.patch("/{device_id}/skills/{skill_name}")
async def update_skill(device_id: str, skill_name: str, body: SkillUpdateRequest, request: Request):
    """启用或禁用技能"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        result = await manager.send_request(device_id, "skills.update", {
            "name": skill_name,
            "disabled": not body.enabled,
        })
        payload = result.get("data") or {}
        return {"success": True, "skill": payload.get("skill", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SkillInstallRequest(BaseModel):
    name: str
    version: Optional[str] = None


@router.post("/{device_id}/skills/install")
async def install_skill(device_id: str, body: SkillInstallRequest, request: Request):
    """从 ClawHub 安装技能"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    try:
        params = {"name": body.name}
        if body.version:
            params["version"] = body.version
        result = await manager.send_request(device_id, "skills.install", params)
        payload = result.get("data") or {}
        return {"success": True, "result": payload}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
