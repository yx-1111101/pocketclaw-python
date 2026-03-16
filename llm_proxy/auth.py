"""设备认证模块"""
import hmac
import hashlib
from typing import Optional, Tuple
from fastapi import Header, HTTPException, Request


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
    request: Request,
    x_device_id: Optional[str] = Header(None, alias="X-Device-Id"),
) -> Tuple[str, int, str]:
    if not x_device_id:
        print(f"[auth] 401 missing X-Device-Id header | ip={request.client.host} path={request.url.path}")
        raise HTTPException(status_code=401, detail="Missing X-Device-Id header")
    print(f"[auth] device={x_device_id} ip={request.client.host}")
    return x_device_id, 0, ""
