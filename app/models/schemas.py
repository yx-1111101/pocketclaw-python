"""Pydantic 数据模型"""
from typing import Optional
from pydantic import BaseModel

class HeartbeatRequest(BaseModel):
    device_id: str
    public_url: Optional[str] = None
    pairing_code_hash: Optional[str] = None
    pairing_code_expires: Optional[int] = None
    firmware_version: Optional[str] = None
    timestamp: Optional[int] = None
    device_secret_hash: Optional[str] = None
    device_secret: Optional[str] = None  # 首次注册时携带明文，云端存储后用于 HMAC 验签

class BindRequest(BaseModel):
    device_id: str
    user_id: str
    pairing_code: Optional[str] = None

class WechatLoginRequest(BaseModel):
    code: str
    encrypted_data: Optional[str] = None
    iv: Optional[str] = None

class WechatBindPhoneRequest(BaseModel):
    openid: str
    phone: Optional[str] = None
