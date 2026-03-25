"""微信登录 + 短信验证码 API 路由"""
import uuid
from typing import Any, Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import WECHAT_APP_ID, WECHAT_APP_SECRET
from app.core.security import make_auth_token
from app.core.sms import check_code, send_verification_code, verify_code
from app.core.db import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


# ============== 微信登录 ==============

class WechatLoginRequest(BaseModel):
    code: str
    encrypted_data: Optional[str] = None
    iv: Optional[str] = None


class SendCodeRequest(BaseModel):
    phone: str


class VerifyCodeRequest(BaseModel):
    phone: str
    code: str


class PhoneLoginRequest(BaseModel):
    phone: str
    code: str


class BindPhoneRequest(BaseModel):
    openid: str
    phone: str
    code: str


def normalize_phone(phone: str = "") -> str:
    value = str(phone or "").strip()
    return value


def is_valid_phone(phone: str = "") -> bool:
    value = normalize_phone(phone)
    return len(value) == 11 and value.startswith("1") and value.isdigit()


def make_user_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def db_is_ready(db: Any) -> bool:
    return bool(db and getattr(db, "url", ""))


def is_unique_violation_error(err: Exception) -> bool:
    text = str(err or "").lower()
    return (
        "duplicate key" in text
        or "unique constraint" in text
        or "already exists" in text
        or "23505" in text
    )


async def fetch_single_user(db: Any, filters: dict) -> Optional[dict]:
    result = await db.get("users", filters)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(result["error"])
    if not result or isinstance(result, dict):
        return None
    if len(result) > 1:
        raise ValueError("matched multiple users")
    return result[0]


async def insert_user(db: Any, payload: dict) -> dict:
    result = await db.post("users", payload)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(result["error"])
    if isinstance(result, list) and result:
        return result[0]
    return payload


async def patch_user(db: Any, filters: dict, payload: dict) -> None:
    result = await db.patch("users", filters, payload)
    if isinstance(result, dict) and result.get("error"):
        raise RuntimeError(result["error"])


async def ensure_user_id(db: Any, user: dict, filters: dict, prefix: str) -> str:
    user_id = str(user.get("user_id") or "").strip()
    if user_id:
        return user_id
    user_id = make_user_id(prefix)
    await patch_user(db, filters, {"user_id": user_id})
    user["user_id"] = user_id
    return user_id


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
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, params=params)
            result = resp.json()

            if "openid" not in result:
                return {"success": False, "error": result.get("errmsg", "获取 openid 失败")}

            openid = result["openid"]
            user_id = f"wx_{openid[:16]}"
            phone = ""

            db = get_db()
            if not db_is_ready(db):
                return {"success": False, "error": "数据库未配置，无法完成微信登录"}

            try:
                existing = await fetch_single_user(db, {"openid": openid})
                if existing:
                    user_id = existing.get("user_id") or user_id
                    phone = normalize_phone(existing.get("phone", ""))
                    if not existing.get("user_id"):
                        await patch_user(db, {"openid": openid}, {"user_id": user_id})
                    if is_valid_phone(phone):
                        # 当手机号已归属到其他 user_id 时，以手机号用户为准，保证数据一致。
                        phone_owner = await fetch_single_user(db, {"phone": phone})
                        if phone_owner:
                            user_id = await ensure_user_id(db, phone_owner, {"phone": phone}, "ph")
                else:
                    created = await insert_user(
                        db,
                        {
                            "user_id": user_id,
                            "openid": openid,
                            "phone": "",
                        },
                    )
                    user_id = created.get("user_id", user_id)
                    phone = normalize_phone(created.get("phone", ""))
            except ValueError:
                return {"success": False, "error": "该微信账号存在重复用户，请联系管理员"}
            except Exception as e:
                return {"success": False, "error": f"微信登录数据库操作失败: {e}"}

            return {
                "success": True,
                "data": {
                    "openid": openid,
                    "user_id": user_id,
                    "phone": phone,
                    "need_bind_phone": not is_valid_phone(phone),
                    "token": make_auth_token(user_id),
                }
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ============== 短信验证码 ==============

@router.post("/send-code")
async def send_sms_code(data: SendCodeRequest):
    """发送短信验证码"""
    return await send_verification_code(normalize_phone(data.phone))


@router.post("/verify-code")
async def verify_sms_code(data: VerifyCodeRequest):
    """校验短信验证码（不消费验证码）"""
    phone = normalize_phone(data.phone)
    if not is_valid_phone(phone):
        return {"success": False, "error": "手机号格式不正确"}
    if not data.code:
        return {"success": False, "error": "验证码不能为空"}

    is_valid = check_code(phone, data.code)
    if is_valid:
        return {"success": True, "message": "验证成功"}
    else:
        return {"success": False, "error": "验证码错误或已过期"}


@router.post("/phone-login")
async def phone_login(data: PhoneLoginRequest):
    """手机号登录：验证码通过后，查找或创建用户"""
    phone = normalize_phone(data.phone)
    if not is_valid_phone(phone):
        return {"success": False, "error": "手机号格式不正确"}
    if not data.code:
        return {"success": False, "error": "验证码不能为空"}
    if not verify_code(phone, data.code):
        return {"success": False, "error": "验证码错误或已过期"}

    db = get_db()
    if not db_is_ready(db):
        return {"success": False, "error": "数据库未配置，无法完成手机号登录"}

    try:
        user = await fetch_single_user(db, {"phone": phone})
        if not user:
            try:
                user = await insert_user(db, {
                    "user_id": make_user_id("ph"),
                    "phone": phone,
                })
            except Exception as e:
                # 并发首次登录时，另一个请求可能刚创建成功；回查即可。
                if not is_unique_violation_error(e):
                    raise
                user = await fetch_single_user(db, {"phone": phone})
                if not user:
                    raise
        user_id = await ensure_user_id(db, user, {"phone": phone}, "ph")
        return {
            "success": True,
            "message": "登录成功",
            "data": {
                "user_id": user_id,
                "openid": user.get("openid", ""),
                "phone": phone,
                "need_bind_phone": False,
                "token": make_auth_token(user_id),
            },
        }
    except ValueError:
        return {"success": False, "error": "该手机号存在多个账号，请联系管理员"}
    except Exception as e:
        return {"success": False, "error": f"手机号登录失败: {e}"}


@router.post("/bind-phone")
async def bind_phone(data: BindPhoneRequest):
    """绑定手机号（需要先验证验证码）"""
    if not data.openid:
        return {"success": False, "error": "openid 不能为空"}
    phone = normalize_phone(data.phone)
    if not is_valid_phone(phone):
        return {"success": False, "error": "手机号格式不正确"}
    if not data.code:
        return {"success": False, "error": "验证码不能为空"}
    if not verify_code(phone, data.code):
        return {"success": False, "error": "验证码错误或已过期"}

    db = get_db()
    if not db_is_ready(db):
        return {"success": False, "error": "数据库未配置，无法完成绑定"}

    try:
        openid_user = await fetch_single_user(db, {"openid": data.openid})
        phone_user = await fetch_single_user(db, {"phone": phone})

        # 手机号已存在时，始终以手机号用户为准，保证同手机号落到同一 user_id。
        if phone_user:
            user = phone_user
            user_id = await ensure_user_id(db, user, {"phone": phone}, "ph")

            # 仅在手机号用户尚未记录 openid 时做一次补全，避免覆盖已有值。
            current_openid = str(user.get("openid") or "").strip()
            if not current_openid and data.openid:
                await patch_user(db, {"phone": phone}, {"openid": data.openid})
                user["openid"] = data.openid
            user["phone"] = phone
        elif openid_user:
            user = openid_user
            user_id = await ensure_user_id(db, user, {"openid": data.openid}, "wx")
            await patch_user(db, {"openid": data.openid}, {"phone": phone})
            user["phone"] = phone
        else:
            user = await insert_user(db, {
                "user_id": f"wx_{data.openid[:16]}",
                "openid": data.openid,
                "phone": phone,
            })
            user_id = user.get("user_id", f"wx_{data.openid[:16]}")
    except ValueError:
        return {"success": False, "error": "用户数据异常（存在重复记录），请联系管理员"}
    except Exception as e:
        return {"success": False, "error": f"绑定失败: {e}"}

    return {
        "success": True,
        "message": "绑定成功",
        "data": {
            "openid": user.get("openid", data.openid),
            "user_id": user_id,
            "phone": phone,
            "need_bind_phone": False,
            "token": make_auth_token(user_id),
        },
    }


@router.get("/user/{user_id}")
async def get_user(user_id: str):
    """获取用户信息"""
    db = get_db()
    if not db_is_ready(db):
        return {"success": False, "error": "数据库未配置，无法查询用户"}

    users = await db.get("users", {"user_id": user_id})
    if isinstance(users, dict) and users.get("error"):
        return {"success": False, "error": f"查询用户失败: {users['error']}"}
    if not users or isinstance(users, dict):
        return {"success": False, "error": "用户不存在"}
    if len(users) > 1:
        return {"success": False, "error": "用户数据异常（存在重复记录）"}

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
