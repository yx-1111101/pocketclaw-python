"""微信登录 API 路由"""
import httpx
import json
import base64
from Crypto.Cipher import AES
from fastapi import APIRouter
from app.core.redis_db import get_db
from app.config import WECHAT_APP_ID, WECHAT_APP_SECRET
from app.models.schemas import WechatLoginRequest, WechatBindPhoneRequest

router = APIRouter(prefix="/api/auth", tags=["微信"])


def decrypt_phone_number(code: str, encrypted_data: str, iv: str) -> str:
    """解密手机号（需要 session_key）"""
    return ""


async def get_phone_by_code(appid: str, code: str) -> str:
    """通过手机号获取凭证获取真实手机号"""
    url = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
    params = {"access_token": code}  # 注意：这里需要用 access_token，不是 code
    # 实际应该先通过 code 获取 session_key，再解密
    return ""


@router.post("/login")
async def wechat_login(data: WechatLoginRequest):
    db = get_db()
    
    # 1. 调用微信 jscode2session 获取 openid 和 session_key
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "js_code": data.code,
        "grant_type": "authorization_code"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params)
            result = resp.json()
            
            if "openid" not in result:
                return {"success": False, "error": result.get("errmsg", "获取 openid 失败")}
            
            openid = result["openid"]
            session_key = result.get("session_key", "")
            
            # 2. 查询用户
            users = await db.get("users", {"openid": openid})
            phone = ""
            
            if users and not isinstance(users, dict) and len(users) > 0:
                # 用户存在，获取手机号
                user = users[0]
                user_id = user["user_id"]
                phone = user.get("phone", "")
            else:
                # 新用户，创建记录
                user_id = f"wx_{openid[:16]}"
                await db.post("users", {"user_id": user_id, "openid": openid})
            
            # 3. 如果有 encryptedData，尝试解密获取手机号
            if data.encrypted_data and session_key:
                try:
                    phone = decrypt_wechat_phone(session_key, data.encrypted_data, data.iv or "")
                    # 更新手机号
                    if phone:
                        await db.patch("users", {"openid": openid}, {"phone": phone})
                except:
                    pass  # 解密失败不影响登录
            
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


def decrypt_wechat_phone(session_key: str, encrypted_data: str, iv: str) -> str:
    """解密微信手机号"""
    try:
        # base64 解码
        session_key_bytes = base64.b64decode(session_key)
        encrypted_data_bytes = base64.b64decode(encrypted_data)
        iv_bytes = base64.b64decode(iv)
        
        # AES 解密
        cipher = AES.new(session_key_bytes, AES.MODE_CBC, iv_bytes)
        decrypted = cipher.decrypt(encrypted_data_bytes)
        
        # 去除 padding
        pad_length = decrypted[-1]
        decrypted = decrypted[:-pad_length]
        
        # 解析 JSON
        data = json.loads(decrypted.decode('utf-8'))
        return data.get("phoneNumber", "")
    except:
        return ""


@router.post("/bind-phone")
async def wechat_bind_phone(data: WechatBindPhoneRequest):
    db = get_db()
    
    if not data.openid:
        return {"success": False, "error": "openid 不能为空"}
    
    users = await db.get("users", {"openid": data.openid})
    if not users or (isinstance(users, dict) and "error" in users):
        return {"success": False, "error": "用户不存在，请先登录"}
    
    # 更新手机号
    update_data = {}
    if data.phone:
        update_data["phone"] = data.phone
    
    if update_data:
        await db.patch("users", {"openid": data.openid}, update_data)
    
    return {"success": True}


@router.get("/user/{user_id}")
async def get_wechat_user(user_id: str):
    db = get_db()
    users = await db.get("users", {"user_id": user_id})
    if not users or (isinstance(users, dict) and "error" in users):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    
    user = users[0]
    return {
        "user_id": user["user_id"],
        "openid": user.get("openid", ""),
        "phone": user.get("phone", ""),
        "nickname": user.get("nickname", ""),
        "avatar": user.get("avatar", "")
    }
