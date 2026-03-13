"""微信登录 API 路由 - 简化版"""
import httpx
import json
from fastapi import APIRouter
from app.config import WECHAT_APP_ID, WECHAT_APP_SECRET
from app.models.schemas import WechatLoginRequest, WechatBindPhoneRequest

router = APIRouter(prefix="/api/auth", tags=["微信"])


@router.post("/login")
async def wechat_login(data: WechatLoginRequest):
    """微信登录 - 获取 openid"""
    
    # 1. 调用微信 jscode2session 获取 openid
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "js_code": data.code,
        "grant_type": "authorization_code"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params)
            result = resp.json()
            
            if "openid" not in result:
                return {"success": False, "error": result.get("errmsg", "获取 openid 失败")}
            
            openid = result["openid"]
            session_key = result.get("session_key", "")
            
            # 2. 生成 user_id
            user_id = f"wx_{openid[:16]}"
            
            # 3. 如果有手机号凭证，调用微信 API 获取手机号
            phone = ""
            if data.encrypted_data and session_key:
                phone = await get_wechat_phone(WECHAT_APP_ID, session_key, data.encrypted_data, data.iv)
            
            return {
                "success": True,
                "data": {
                    "openid": openid,
                    "user_id": user_id,
                    "phone": phone,
                    "need_bind_phone": not phone
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_wechat_phone(appid: str, session_key: str, encrypted_data: str, iv: str) -> str:
    """通过微信开放能力获取手机号（需要企业认证）"""
    # 注意：这个接口需要微信企业认证
    # 个人小程序可能无法使用
    # 暂时返回空字符串，让用户手动输入
    return ""


@router.post("/bind-phone")
async def wechat_bind_phone(data: WechatBindPhoneRequest):
    """绑定手机号（简化版 - 直接存储）"""
    
    if not data.openid:
        return {"success": False, "error": "openid 不能为空"}
    
    if not data.phone:
        return {"success": False, "error": "手机号不能为空"}
    
    # 这里应该更新数据库，暂时返回成功
    return {"success": True}


@router.get("/user/{user_id}")
async def get_wechat_user(user_id: str):
    """获取用户信息"""
    # 这里应该查询数据库，暂时返回模拟数据
    return {
        "user_id": user_id,
        "openid": "",
        "phone": "",
        "nickname": "",
        "avatar": ""
    }
