"""微信登录 + 短信验证码 API 路由"""
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from app.config import WECHAT_APP_ID, WECHAT_APP_SECRET
from app.core.sms import send_verification_code, verify_code

router = APIRouter(prefix="/api/auth", tags=["认证"])


# ============== 微信登录 ==============

class WechatLoginRequest(BaseModel):
    code: str
    encrypted_data: str = None
    iv: str = None


@router.post("/login")
async def wechat_login(data: WechatLoginRequest):
    """微信登录 - 获取 openid"""
    
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
            user_id = f"wx_{openid[:16]}"
            
            return {
                "success": True,
                "data": {
                    "openid": openid,
                    "user_id": user_id,
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============== 短信验证码 ==============

class SendCodeRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


@router.post("/send-code")
async def send_sms_code(data: SendCodeRequest):
    """发送短信验证码"""
    return await send_verification_code(data.phone)


@router.post("/verify-code")
async def verify_sms_code(data: VerifyCodeRequest):
    """验证短信验证码"""
    is_valid = verify_code(data.phone, data.code)
    if is_valid:
        return {"success": True, "message": "验证成功"}
    else:
        return {"success": False, "error": "验证码错误或已过期"}


# ============== 绑定手机号 ==============

class BindPhoneRequest(BaseModel):
    openid: str
    phone: str
    code: str  # 短信验证码


@router.post("/bind-phone")
async def bind_phone(data: BindPhoneRequest):
    """绑定手机号（需要先验证验证码）"""
    
    if not data.openid:
        return {"success": False, "error": "openid 不能为空"}
    
    if not data.phone:
        return {"success": False, "error": "手机号不能为空"}
    
    if not data.code:
        return {"success": False, "error": "验证码不能为空"}
    
    # 验证验证码
    if not verify_code(data.phone, data.code):
        return {"success": False, "error": "验证码错误或已过期"}
    
    # 绑定成功（这里应该更新数据库）
    return {"success": True, "message": "绑定成功"}


@router.get("/user/{user_id}")
async def get_user(user_id: str):
    """获取用户信息"""
    return {
        "user_id": user_id,
        "openid": "",
        "phone": "",
        "nickname": "",
        "avatar": ""
    }
