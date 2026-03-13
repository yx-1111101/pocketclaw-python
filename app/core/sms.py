"""腾讯云短信服务"""
import random
import string
import time
import hashlib
import base64
import json
import httpx
from datetime import datetime
from typing import Optional

# 腾讯云配置
TENCENTCLOUD_SECRET_ID = ""  # 你的 SecretId
TENCENTCLOUD_SECRET_KEY = ""  # 你的 SecretKey
SMS_SDK_APPID = ""           # 你的 SmsSdkAppid
SMS_SIGN_NAME = ""           # 你的短信签名
SMS_TEMPLATE_ID = ""         # 你的模板 ID

# 验证码缓存（生产环境用 Redis）
VERIFICATION_CODES = {}


def generate_code(length: int = 6) -> str:
    """生成随机验证码"""
    return ''.join(random.choices(string.digits, k=length))


def get_current_timestamp() -> int:
    """获取当前时间戳（秒）"""
    return int(time.time())


def sign_sha256(secret_key: str, payload: str) -> str:
    """SHA256 签名"""
    import hmac
    signature = hmac.new(
        secret_key.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode('utf-8')


async def send_sms(phone: str, code: str) -> dict:
    """发送短信验证码"""
    
    if not all([TENCENTCLOUD_SECRET_ID, TENCENTCLOUD_SECRET_KEY, SMS_SDK_APPID, SMS_SIGN_NAME, SMS_TEMPLATE_ID]):
        return {"success": False, "error": "短信服务未配置"}
    
    # 构建请求
    endpoint = "sms.tencentcloudapi.com"
    action = "SendSms"
    version = "2019-07-11"
    timestamp = get_current_timestamp()
    nonce = random.randint(100000, 999999)
    
    # 手机号格式：+86xxxxxxxxxx
    phone_number = f"+86{phone.lstrip('+86')}"
    
    # 请求参数
    params = {
        "PhoneNumberSet": [phone_number],
        "SmsSdkAppid": SMS_SDK_APPID,
        "Sign": SMS_SIGN_NAME,
        "TemplateID": SMS_TEMPLATE_ID,
        "TemplateParamSet": [code],
    }
    
    # 签名
    payload = json.dumps(params)
    auth = f"TC3-HMAC-SHA256\n{timestamp}\n{timestamp}/{action}/sms_api\n{payload}"
    signature = sign_sha256(TENCENTCLOUD_SECRET_KEY, auth)
    
    headers = {
        "Content-Type": "application/json",
        "Host": endpoint,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": version,
        "X-TC-Region": "",
        "Authorization": f"TC3-HMAC-SHA256 Credential={TENCENTCLOUD_SECRET_ID}/{timestamp}/{action}/sms_api, SignedHeaders=content-type;host, Signature={signature}"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://{endpoint}/",
                headers=headers,
                content=payload,
                timeout=10.0
            )
            result = resp.json()
            
            # 检查返回
            if "Response" in result:
                status = result["Response"].get("SendStatusSet", [{}])[0]
                if status.get("Code") == "Ok":
                    return {"success": True, "message": "发送成功"}
                else:
                    return {"success": False, "error": status.get("Message", "发送失败")}
            else:
                return {"success": False, "error": str(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def save_verification_code(phone: str, code: str, expire_seconds: int = 300) -> None:
    """保存验证码"""
    VERIFICATION_CODES[phone] = {
        "code": code,
        "expire_time": time.time() + expire_seconds
    }


def verify_code(phone: str, code: str) -> bool:
    """验证验证码"""
    if phone not in VERIFICATION_CODES:
        return False
    
    record = VERIFICATION_CODES[phone]
    
    # 检查是否过期
    if time.time() > record["expire_time"]:
        del VERIFICATION_CODES[phone]
        return False
    
    # 验证并删除（一次性）
    is_valid = record["code"] == code
    if is_valid:
        del VERIFICATION_CODES[phone]
    
    return is_valid


async def send_verification_code(phone: str) -> dict:
    """发送验证码"""
    # 验证手机号格式
    if not phone or len(phone) != 11 or not phone.startswith('1'):
        return {"success": False, "error": "手机号格式不正确"}
    
    # 检查是否频繁发送（60秒内只能发一次）
    if phone in VERIFICATION_CODES:
        record = VERIFICATION_CODES[phone]
        if time.time() < record["expire_time"] - 240:  # 5分钟有效，但60秒内不能重复发
            return {"success": False, "error": "发送太频繁，请稍后再试"}
    
    # 生成验证码
    code = generate_code()
    
    # 发送短信
    result = await send_sms(phone, code)
    
    if result["success"]:
        save_verification_code(phone, code)
    
    return result
