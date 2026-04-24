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
    user_id: Optional[str] = None
    pairing_code: Optional[str] = None

class WechatLoginRequest(BaseModel):
    code: str
    encrypted_data: Optional[str] = None
    iv: Optional[str] = None

class WechatBindPhoneRequest(BaseModel):
    openid: str
    phone: Optional[str] = None


class GatewayRegisterRequest(BaseModel):
    device_id: Optional[str] = None
    source_type: str = "gateway"
    runtime: Optional[str] = None
    firmware_version: Optional[str] = None


class GatewayPairRequest(BaseModel):
    credential_code: str
    source: Optional[str] = None


class GatewayUpdateRequest(BaseModel):
    display_name: Optional[str] = None
