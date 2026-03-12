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

class BindRequest(BaseModel):
    device_id: str
    user_id: str
    pairing_code: Optional[str] = None

class WechatLoginRequest(BaseModel):
    code: str

class WechatBindPhoneRequest(BaseModel):
    openid: str
    phone: str
    code: str
