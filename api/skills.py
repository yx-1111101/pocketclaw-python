"""Skills 管理 API（调用本地 Gateway WS）"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.core.gateway_client import gateway_request

router = APIRouter(prefix="/system/skills", tags=["技能管理"])


@router.get("")
async def list_skills():
    """获取所有技能列表"""
    try:
        payload = await gateway_request("skills.status", {})
        skills = payload.get("skills", [])
        return {
            "success": True,
            "skills": [
                {
                    "name": s.get("name"),
                    "description": s.get("description", "").split("\n")[0],  # 只取第一行
                    "enabled": not s.get("disabled", False),
                    "eligible": s.get("eligible", True),
                    "source": s.get("source", ""),
                    "always": s.get("always", False),
                }
                for s in skills
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SkillUpdateRequest(BaseModel):
    enabled: bool


@router.patch("/{skill_name}")
async def update_skill(skill_name: str, body: SkillUpdateRequest):
    """启用或禁用技能"""
    try:
        payload = await gateway_request("skills.update", {
            "name": skill_name,
            "disabled": not body.enabled,
        })
        return {"success": True, "skill": payload.get("skill", {})}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SkillInstallRequest(BaseModel):
    name: str           # skill name on clawhub
    version: Optional[str] = None


@router.post("/install")
async def install_skill(body: SkillInstallRequest):
    """从 ClawHub 安装技能"""
    try:
        params = {"name": body.name}
        if body.version:
            params["version"] = body.version
        payload = await gateway_request("skills.install", params)
        return {"success": True, "result": payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
