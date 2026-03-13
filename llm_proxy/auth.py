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
        device_secret: str
    ) -> bool:
        """
        验证设备签名

        Args:
            device_id: 设备 ID
            timestamp: Unix 时间戳（秒）
            signature: 客户端提供的签名
            device_secret: 设备密钥（明文）

        Returns:
            签名是否有效
        """
        # 检查时间戳是否在容差范围内
        current_time = int(time.time())
        if abs(current_time - timestamp) > DeviceAuth.TIMESTAMP_TOLERANCE:
            return False

        # 计算期望的签名
        message = f"{device_id}:{timestamp}"
        expected_signature = hmac.new(
            device_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        # 使用常量时间比较防止时序攻击
        return hmac.compare_digest(signature, expected_signature)

    @staticmethod
    def generate_signature(device_id: str, timestamp: int, device_secret: str) -> str:
        """
        生成签名（用于测试）

        Args:
            device_id: 设备 ID
            timestamp: Unix 时间戳（秒）
            device_secret: 设备密钥

        Returns:
            HMAC-SHA256 签名
        """
        message = f"{device_id}:{timestamp}"
        return hmac.new(
            device_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()


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
