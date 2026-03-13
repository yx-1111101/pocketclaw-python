"""微信登录 + 短信验证码 API 路由"""
import httpx
from fastapi import APIRouter
from pydantic import BaseModel
from app.config import WECHAT_APP_ID, WECHAT_APP_SECRET
from app.core.sms import send_verification_code, verify_code
from app.core.supabase import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


# ============== 微信登录 ==============

class WechatLoginRequest(BaseModel):
    code: str
    encrypted_data: str = None
    iv: str = None

def is_valid_phone(phone: str = "") -> bool:
    value = str(phone or "").strip()
    return len(value) == 11 and value.startswith("1") and value.isdigit()


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
            phone = ""

            # 尝试从数据库读取（Supabase 未配置时跳过）
            db = get_db()
            if db and db.url:
                try:
                    users = await db.get("users", {"openid": openid})
                    existing = users[0] if users and not isinstance(users, dict) else None
                    if existing:
                        user_id = existing.get("user_id") or user_id
                        phone = existing.get("phone") or ""
                    else:
                        await db.post("users", {
                            "user_id": user_id,
                            "openid": openid,
                            "phone": "",
                        })
                except Exception:
                    pass  # 数据库操作失败不影响登录
            
            return {
                "success": True,
                "data": {
                    "openid": openid,
                    "user_id": user_id,
                    "phone": phone,
                    "need_bind_phone": not is_valid_phone(phone),
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
    
    db = get_db()
    users = await db.get("users", {"openid": data.openid})
    if isinstance(users, dict) and users.get("error"):
        return {"success": False, "error": "查询用户失败"}

    user_id = f"wx_{data.openid[:16]}"
    if users and not isinstance(users, dict):
        user = users[0]
        user_id = user.get("user_id") or user_id
        updated = await db.patch(
            "users",
            {"openid": data.openid},
            {
                "phone": data.phone,
                "user_id": user_id,
            },
        )
        if isinstance(updated, dict) and updated.get("error"):
            return {"success": False, "error": "更新手机号失败"}
    else:
        created = await db.post(
            "users",
            {
                "user_id": user_id,
                "openid": data.openid,
                "phone": data.phone,
            },
        )
        if isinstance(created, dict) and created.get("error"):
            return {"success": False, "error": "绑定手机号失败"}

    return {
        "success": True,
        "message": "绑定成功",
        "data": {
            "openid": data.openid,
            "user_id": user_id,
            "phone": data.phone,
            "need_bind_phone": False,
        },
    }


@router.get("/user/{user_id}")
async def get_user(user_id: str):
    """获取用户信息"""
    db = get_db()
    users = await db.get("users", {"user_id": user_id})
    if isinstance(users, dict) and users.get("error"):
        return {"success": False, "error": "查询用户失败"}
    if not users or isinstance(users, dict):
        return {"success": False, "error": "用户不存在"}

    user = users[0]
    return {
        "success": True,
        "data": {
            "user_id": user.get("user_id", user_id),
            "openid": user.get("openid", ""),
            "phone": user.get("phone", ""),
            "nickname": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
        },
    }
