"""Gateway 管理 API"""
import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.security import hash_sha256, extract_bearer_token, parse_auth_token, parse_user_from_auth_header
from app.core.db import get_db
from app.models.schemas import GatewayRegisterRequest, GatewayPairRequest, GatewayUpdateRequest
from api.device import is_online

router = APIRouter(prefix="/api/gateways", tags=["Gateway 管理"])
logger = logging.getLogger("uvicorn.error")

# 去掉易混淆字符 O/0/I/1
_CREDENTIAL_CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CREDENTIAL_LENGTH = 8
_CREDENTIAL_TTL_MINUTES = 30
_CREDENTIAL_MAX_ATTEMPTS = 5


# ── 辅助函数 ──────────────────────────────────────────────────────

def _gateway_error(code: str, message: str, status: int = 400):
    return JSONResponse(
        {"success": False, "error": {"code": code, "message": message}},
        status_code=status,
    )


def _generate_credential_code() -> str:
    return "".join(secrets.choice(_CREDENTIAL_CHARSET) for _ in range(_CREDENTIAL_LENGTH))


async def _create_credential(db, device_id: str, runtime: str = None) -> dict:
    code = _generate_credential_code()
    code_hash = hash_sha256(code)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_CREDENTIAL_TTL_MINUTES)

    result = await db.post("pairing_credentials", {
        "device_id": device_id,
        "credential_code": code,
        "credential_hash": code_hash,
        "runtime": runtime or "",
        "expires_at": expires_at.isoformat(),
        "attempt_count": 0,
        "max_attempts": _CREDENTIAL_MAX_ATTEMPTS,
        "used": 0,
        "invalidated": 0,
    })
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=500, detail=f"创建凭证失败: {result['error']}")

    qr_payload = f"friday://pair?code={code}&runtime={runtime or ''}&device_id={device_id}"
    return {
        "credential_code": code,
        "expires_at": expires_at.isoformat(),
        "expires_in_seconds": _CREDENTIAL_TTL_MINUTES * 60,
        "qr_payload": qr_payload,
    }


async def _invalidate_device_credentials(db, device_id: str):
    """作废该设备所有未使用的凭证"""
    creds = await db.get("pairing_credentials", {"device_id": device_id})
    if isinstance(creds, dict) and creds.get("error"):
        return
    if not creds or isinstance(creds, dict):
        return
    for cred in creds:
        if not cred.get("used") and not cred.get("invalidated"):
            await db.patch(
                "pairing_credentials",
                {"id": cred["id"]},
                {"invalidated": 1},
            )


async def _fetch_single(db, table: str, filters: dict):
    rows = await db.get(table, filters)
    if isinstance(rows, dict) and rows.get("error"):
        raise HTTPException(status_code=500, detail=f"查询 {table} 失败: {rows['error']}")
    if not rows or isinstance(rows, dict):
        return None
    return rows[0]


async def _require_auth_user(db, request: Request) -> dict:
    user_id, err = parse_user_from_auth_header(request.headers.get("Authorization", ""))
    if err:
        raise HTTPException(status_code=401, detail=err)
    user = await _fetch_single(db, "users", {"user_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="token 对应用户不存在")
    return user


def _normalize_gateway(device: dict, binding: dict = None) -> dict:
    """标准化 API 响应中的 gateway 对象"""
    return {
        "device_id": device.get("device_id", ""),
        "display_name": (binding or {}).get("display_name") or device.get("name") or "我的盒子",
        "source_type": device.get("source_type", "legacy"),
        "runtime": device.get("runtime") or None,
        "firmware_version": device.get("firmware_version") or None,
        "is_online": is_online(device),
        "last_used_at": str(device.get("last_used_at") or "") or None,
        "created_at": str(device.get("created_at") or "") or None,
    }


def _parse_device_bearer(request: Request):
    """尝试从 Bearer token 中提取 device_id（设备端用 device_secret 签名的简单 token）。
    这里复用 JWT_SECRET 签发的 token，payload 中带 device_id 字段。
    返回 (device_id, error_msg)。"""
    token = extract_bearer_token(request.headers.get("Authorization", ""))
    if not token:
        return None, None
    try:
        payload = parse_auth_token(token)
        device_id = str(payload.get("device_id") or payload.get("user_id") or "").strip()
        return device_id if device_id else None, None
    except Exception as e:
        return None, str(e)


# ── 端点 ──────────────────────────────────────────────────────────

@router.post("/register")
async def register_gateway(data: GatewayRegisterRequest, request: Request):
    """设备注册 & 凭证获取。

    场景：
    - 无 device_id → 首次注册（云端分配 gw-xxx）
    - 有 device_id + 无 DB 记录 → Friday 首次注册（用提供的 device_id）
    - 有 device_id + 有 DB 记录 + 无 secret → 存量设备升级
    - 有 device_id + Bearer auth → 刷新凭证
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # 检查是否带 Bearer（已注册设备刷新凭证）
    bearer_device_id, bearer_err = _parse_device_bearer(request)
    if bearer_err:
        return _gateway_error("INVALID_TOKEN", bearer_err, 401)

    if bearer_device_id:
        # 已认证设备 → 刷新凭证
        device = await _fetch_single(db, "devices", {"device_id": bearer_device_id})
        if not device:
            return _gateway_error("DEVICE_NOT_FOUND", "设备不存在", 404)

        # 作废旧凭证
        await _invalidate_device_credentials(db, bearer_device_id)

        # 更新设备信息
        update_payload = {"updated_at": now}
        if data.firmware_version:
            update_payload["firmware_version"] = data.firmware_version
        if data.runtime:
            update_payload["runtime"] = data.runtime
        await db.patch("devices", {"device_id": bearer_device_id}, update_payload)

        credential = await _create_credential(db, bearer_device_id, data.runtime)
        return {
            "success": True,
            "device_id": bearer_device_id,
            "credential": credential,
        }

    # 无 Bearer 认证
    device_id = (data.device_id or "").strip()

    if device_id:
        # 有 device_id → 检查是否已存在
        device = await _fetch_single(db, "devices", {"device_id": device_id})

        if device:
            # 存量设备升级：已有记录但无 secret
            if device.get("device_secret_hash"):
                return _gateway_error(
                    "ALREADY_REGISTERED",
                    "该设备已注册且有密钥，请使用 Bearer 认证刷新凭证",
                    409,
                )

            # 分配 secret
            device_secret = secrets.token_urlsafe(32)
            secret_hash = hash_sha256(device_secret)
            update_payload = {
                "device_secret_hash": secret_hash,
                "source_type": data.source_type,
                "updated_at": now,
            }
            if data.runtime:
                update_payload["runtime"] = data.runtime
            if data.firmware_version:
                update_payload["firmware_version"] = data.firmware_version
            await db.patch("devices", {"device_id": device_id}, update_payload)

            await _invalidate_device_credentials(db, device_id)
            credential = await _create_credential(db, device_id, data.runtime)

            return {
                "success": True,
                "device_id": device_id,
                "device_secret": device_secret,
                "credential": credential,
            }
        # else: 不存在 → 按提供的 device_id 新建（Friday 模式）
    else:
        # 无 device_id → 云端分配
        device_id = f"gw-{uuid.uuid4().hex[:12]}"

    # 新建设备
    device_secret = secrets.token_urlsafe(32)
    secret_hash = hash_sha256(device_secret)
    result = await db.post("devices", {
        "device_id": device_id,
        "device_secret_hash": secret_hash,
        "source_type": data.source_type,
        "runtime": data.runtime or "",
        "firmware_version": data.firmware_version or "",
        "status": "offline",
        "last_seen": now,
        "created_at": now,
        "updated_at": now,
    })
    if isinstance(result, dict) and result.get("error"):
        return _gateway_error("DB_ERROR", f"设备创建失败: {result['error']}", 500)

    credential = await _create_credential(db, device_id, data.runtime)

    return {
        "success": True,
        "device_id": device_id,
        "device_secret": device_secret,
        "credential": credential,
    }


@router.post("/pair")
async def pair_gateway(data: GatewayPairRequest, request: Request):
    """客户端提交配对码，绑定 Gateway。"""
    db = get_db()
    user = await _require_auth_user(db, request)
    user_id = str(user.get("user_id") or "").strip()

    code = (data.credential_code or "").strip().upper()
    if not code or len(code) != _CREDENTIAL_LENGTH:
        return _gateway_error("INVALID_CODE", f"配对码必须是 {_CREDENTIAL_LENGTH} 位", 400)

    code_hash = hash_sha256(code)

    # 查找凭证
    cred = await _fetch_single(db, "pairing_credentials", {"credential_hash": code_hash})
    if not cred:
        return _gateway_error("CREDENTIAL_NOT_FOUND", "配对码无效", 404)

    # 校验有效性
    if cred.get("invalidated"):
        return _gateway_error("CREDENTIAL_INVALIDATED", "该配对码已作废", 410)
    if cred.get("used"):
        return _gateway_error("CREDENTIAL_USED", "该配对码已被使用", 410)

    # 检查过期
    expires_at = cred.get("expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        else:
            exp_dt = expires_at
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp_dt:
            return _gateway_error("CREDENTIAL_EXPIRED", "配对码已过期", 410)

    # 检查尝试次数
    attempt_count = int(cred.get("attempt_count") or 0)
    max_attempts = int(cred.get("max_attempts") or _CREDENTIAL_MAX_ATTEMPTS)
    if attempt_count >= max_attempts:
        return _gateway_error("MAX_ATTEMPTS_EXCEEDED", "配对码尝试次数已用尽", 429)

    # 递增尝试次数（先读后写）
    await db.patch(
        "pairing_credentials",
        {"id": cred["id"]},
        {"attempt_count": attempt_count + 1},
    )

    device_id = str(cred.get("device_id") or "").strip()
    if not device_id:
        return _gateway_error("INVALID_CREDENTIAL", "凭证数据异常", 500)

    # 检查设备是否存在
    device = await _fetch_single(db, "devices", {"device_id": device_id})
    if not device:
        return _gateway_error("DEVICE_NOT_FOUND", "设备不存在", 404)

    # 检查是否已绑定
    existing = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})
    if existing:
        # 已绑定，标记凭证为已使用
        await db.patch("pairing_credentials", {"id": cred["id"]}, {"used": 1})
        return {
            "success": True,
            "already_bound": True,
            "gateway": _normalize_gateway(device, existing),
        }

    # 创建绑定
    bind_result = await db.post("device_bindings", {
        "user_id": user_id,
        "device_id": device_id,
        "role": "owner",
        "display_name": None,
    })
    if isinstance(bind_result, dict) and bind_result.get("error"):
        return _gateway_error("DB_ERROR", f"绑定失败: {bind_result['error']}", 500)

    # 标记凭证为已使用
    await db.patch("pairing_credentials", {"id": cred["id"]}, {"used": 1})

    # 更新 last_used_at
    now = datetime.now(timezone.utc).isoformat()
    await db.patch("devices", {"device_id": device_id}, {"last_used_at": now})

    binding = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})

    logger.info("[gateway.pair] success user_id=%s device_id=%s", user_id, device_id)
    return {
        "success": True,
        "already_bound": False,
        "gateway": _normalize_gateway(device, binding),
    }


@router.get("")
async def list_gateways(request: Request):
    """用户 Gateway 列表（按 last_used_at DESC 排序）。"""
    db = get_db()
    user = await _require_auth_user(db, request)
    user_id = str(user.get("user_id") or "").strip()

    bindings = await db.get("device_bindings", {"user_id": user_id})
    if isinstance(bindings, dict) and bindings.get("error"):
        raise HTTPException(status_code=500, detail=f"查询绑定关系失败: {bindings['error']}")
    if not bindings or isinstance(bindings, dict):
        return {"success": True, "gateways": []}

    gateways = []
    for binding in bindings:
        device_id = str(binding.get("device_id") or "").strip()
        if not device_id:
            continue
        device = await _fetch_single(db, "devices", {"device_id": device_id})
        if not device:
            continue
        gateways.append(_normalize_gateway(device, binding))

    # 按 last_used_at DESC 排序（None 排最后）
    gateways.sort(key=lambda g: g.get("last_used_at") or "", reverse=True)

    return {"success": True, "gateways": gateways}


@router.get("/{device_id}")
async def get_gateway(device_id: str, request: Request):
    """单个 Gateway 详情。"""
    db = get_db()
    user = await _require_auth_user(db, request)
    user_id = str(user.get("user_id") or "").strip()

    binding = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})
    if not binding:
        return _gateway_error("NOT_BOUND", "你未绑定该 Gateway", 403)

    device = await _fetch_single(db, "devices", {"device_id": device_id})
    if not device:
        return _gateway_error("DEVICE_NOT_FOUND", "设备不存在", 404)

    return {"success": True, "gateway": _normalize_gateway(device, binding)}


@router.put("/{device_id}")
async def update_gateway(device_id: str, data: GatewayUpdateRequest, request: Request):
    """更新 display_name。"""
    db = get_db()
    user = await _require_auth_user(db, request)
    user_id = str(user.get("user_id") or "").strip()

    binding = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})
    if not binding:
        return _gateway_error("NOT_BOUND", "你未绑定该 Gateway", 403)

    update_payload = {}
    if data.display_name is not None:
        update_payload["display_name"] = data.display_name

    if update_payload:
        result = await db.patch("device_bindings", {"user_id": user_id, "device_id": device_id}, update_payload)
        if isinstance(result, dict) and result.get("error"):
            return _gateway_error("DB_ERROR", f"更新失败: {result['error']}", 500)

    device = await _fetch_single(db, "devices", {"device_id": device_id})
    updated_binding = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})

    return {"success": True, "gateway": _normalize_gateway(device or {}, updated_binding)}


@router.delete("/{device_id}")
async def unbind_gateway(device_id: str, request: Request):
    """解绑 Gateway。"""
    db = get_db()
    user = await _require_auth_user(db, request)
    user_id = str(user.get("user_id") or "").strip()

    binding = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})
    if not binding:
        return _gateway_error("NOT_BOUND", "你未绑定该 Gateway", 403)

    result = await db.delete("device_bindings", {"user_id": user_id, "device_id": device_id})
    if isinstance(result, dict) and result.get("error"):
        return _gateway_error("DB_ERROR", f"解绑失败: {result['error']}", 500)

    # 查找建议切换目标
    remaining = await db.get("device_bindings", {"user_id": user_id})
    suggest_device_id = None
    if remaining and not isinstance(remaining, dict):
        # 取第一个剩余的绑定
        for r in remaining:
            rid = str(r.get("device_id") or "").strip()
            if rid and rid != device_id:
                suggest_device_id = rid
                break

    logger.info("[gateway.unbind] user_id=%s device_id=%s suggest=%s", user_id, device_id, suggest_device_id or "-")
    return {
        "success": True,
        "unbound_device_id": device_id,
        "suggest_switch_to": suggest_device_id,
    }


@router.post("/{device_id}/activate")
async def activate_gateway(device_id: str, request: Request):
    """更新 last_used_at（用户切换 Gateway 时调用）。"""
    db = get_db()
    user = await _require_auth_user(db, request)
    user_id = str(user.get("user_id") or "").strip()

    binding = await _fetch_single(db, "device_bindings", {"user_id": user_id, "device_id": device_id})
    if not binding:
        return _gateway_error("NOT_BOUND", "你未绑定该 Gateway", 403)

    now = datetime.now(timezone.utc).isoformat()
    result = await db.patch("devices", {"device_id": device_id}, {"last_used_at": now})
    if isinstance(result, dict) and result.get("error"):
        return _gateway_error("DB_ERROR", f"更新失败: {result['error']}", 500)

    logger.info("[gateway.activate] user_id=%s device_id=%s", user_id, device_id)
    return {"success": True, "device_id": device_id, "last_used_at": now}
