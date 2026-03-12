"""微信登录 API 路由"""
import httpx
from fastapi import APIRouter
from app.core.supabase import get_db
from app.config import WECHAT_APP_ID, WECHAT_APP_SECRET
from app.models.schemas import WechatLoginRequest, WechatBindPhoneRequest

router = APIRouter(prefix="/api/wechat", tags=["微信"])

@router.post("/login")
async def wechat_login(data: WechatLoginRequest):
    db = get_db()
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {"appid": WECHAT_APP_ID, "secret": WECHAT_APP_SECRET, "js_code": data.code, "grant_type": "authorization_code"}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params)
            result = resp.json()
            if "openid" in result:
                openid = result["openid"]
                session_key = result.get("session_key", "")
                users = await db.get("users", {"openid": openid})
                if users and not isinstance(users, dict):
                    user_id = users[0]["user_id"]
                else:
                    user_id = f"wx_{openid[:16]}"
                    await db.post("users", {"user_id": user_id, "openid": openid})
                return {"success": True, "data": {"openid": openid, "user_id": user_id, "session_key": session_key}}
            else:
                return {"success": False, "error": result.get("errmsg", "获取 openid 失败")}
        except Exception as e:
            return {"success": False, "error": str(e)}

@router.post("/bind-phone")
async def wechat_bind_phone(data: WechatBindPhoneRequest):
    db = get_db()
    if len(data.code) != 6 or not data.code.isdigit():
        return {"success": False, "error": "验证码错误"}
    users = await db.get("users", {"openid": data.openid})
    if not users:
        return {"success": False, "error": "用户不存在，请先登录"}
    await db.patch("users", {"openid": data.openid}, {"phone": data.phone})
    return {"success": True}

@router.get("/user/{user_id}")
async def get_wechat_user(user_id: str):
    db = get_db()
    users = await db.get("users", {"user_id": user_id})
    if not users:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    user = users[0]
    return {"user_id": user["user_id"], "openid": user.get("openid", ""), "phone": user.get("phone", ""), "nickname": user.get("nickname", ""), "avatar": user.get("avatar", "")}
