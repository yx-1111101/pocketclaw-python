"""安全工具"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional, Tuple

import os


def hash_sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def _token_secret() -> bytes:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET env var is required for token signing but is not set")
    return secret.encode()


def make_auth_token(user_id: str, ttl_seconds: int = 30 * 24 * 60 * 60) -> str:
    now = int(time.time())
    payload = {
        "user_id": str(user_id or ""),
        "iat": now,
        "exp": now + int(ttl_seconds),
    }
    payload_raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    signature = hmac.new(_token_secret(), payload_raw, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_raw)}.{_b64url_encode(signature)}"


def parse_auth_token(token: str) -> dict:
    text = str(token or "").strip()
    if "." not in text:
        raise ValueError("token 格式不正确")
    payload_part, signature_part = text.split(".", 1)
    payload_raw = _b64url_decode(payload_part)
    signature_raw = _b64url_decode(signature_part)
    expected = hmac.new(_token_secret(), payload_raw, hashlib.sha256).digest()
    if not hmac.compare_digest(signature_raw, expected):
        raise ValueError("token 签名无效")

    payload = json.loads(payload_raw.decode())
    user_id = str(payload.get("user_id") or "").strip()
    exp = int(payload.get("exp") or 0)
    if not user_id:
        raise ValueError("token 缺少用户标识")
    if exp <= int(time.time()):
        raise ValueError("token 已过期")
    return payload


def extract_bearer_token(auth_header: str = "") -> str:
    value = str(auth_header or "").strip()
    if not value.lower().startswith("bearer "):
        return ""
    return value[7:].strip()


def parse_user_from_auth_header(auth_header: str = "") -> Tuple[Optional[str], Optional[str]]:
    token = extract_bearer_token(auth_header)
    if not token:
        return None, "缺少 Bearer token"
    try:
        payload = parse_auth_token(token)
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            return None, "token 缺少用户标识"
        return user_id, None
    except Exception as e:
        return None, f"无效 token: {e}"
