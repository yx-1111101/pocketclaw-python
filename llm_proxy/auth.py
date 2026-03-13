"""设备认证模块 - HMAC-SHA256"""
import hmac
import hashlib
import time
from typing import Tuple
from fastapi import Header, HTTPException


class DeviceAuth:
    """设备 HMAC-SHA256 认证"""

    # 时间戳容差：±300 秒（防重放攻击）
    TIMESTAMP_TOLERANCE = 300

    @staticmethod
    def verify_signature(
        device_id: str,
        timestamp: int,
        signature: str,
        device_secret_hash: str,
    ) -> bool:
        """
        验证设备签名。

        设备签名时用 SHA-256(device_secret) 的原始字节作为 HMAC key，
        云端存储的 device_secret_hash 即为该值的十六进制表示，
        因此云端可直接用 bytes.fromhex(device_secret_hash) 完成验签，
        无需持有明文 secret。
        """
        current_time = int(time.time())
        if abs(current_time - timestamp) > DeviceAuth.TIMESTAMP_TOLERANCE:
            return False

        key = bytes.fromhex(device_secret_hash)
        message = f"{device_id}:{timestamp}"
        expected = hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    @staticmethod
    def generate_signature(device_id: str, timestamp: int, device_secret: str) -> str:
        """生成签名（测试用）。key = SHA-256(device_secret).digest()"""
        key = hashlib.sha256(device_secret.encode("utf-8")).digest()
        message = f"{device_id}:{timestamp}"
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).hexdigest()


async def verify_device_auth(
    x_device_id: str = Header(..., alias="X-Device-Id"),
    x_timestamp: int = Header(..., alias="X-Timestamp"),
    authorization: str = Header(..., alias="Authorization")
) -> Tuple[str, int, str]:
    """
    FastAPI 依赖项：验证设备认证 Header 格式和时间戳

    Headers:
        X-Device-Id: 设备 ID
        X-Timestamp: Unix 时间戳（秒）
        Authorization: HMAC-SHA256 <signature>

    Returns:
        (device_id, timestamp, signature) 元组

    Raises:
        HTTPException: 认证失败
    """
    # 解析 Authorization header
    if not authorization.startswith("HMAC-SHA256 "):
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization format. Expected: HMAC-SHA256 <signature>"
        )

    signature = authorization[12:]  # 移除 "HMAC-SHA256 " 前缀

    # 验证时间戳
    current_time = int(time.time())
    if abs(current_time - x_timestamp) > DeviceAuth.TIMESTAMP_TOLERANCE:
        raise HTTPException(
            status_code=401,
            detail=f"Timestamp out of range. Server time: {current_time}, Client time: {x_timestamp}"
        )

    # 返回解析后的认证信息，由路由处理器从数据库取密钥后完成签名验证
    return x_device_id, x_timestamp, signature
