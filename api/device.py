"""设备 API 路由"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.security import hash_sha256, parse_user_from_auth_header
from app.core.supabase import get_db
from app.models.schemas import BindRequest, HeartbeatRequest

router = APIRouter(prefix="/devices", tags=["设备"])
logger = logging.getLogger("uvicorn.error")


def is_online(device: dict) -> bool:
    if not device:
        return False
    last_seen_ms = _to_epoch_ms(device.get("last_seen"))
    if not last_seen_ms:
        return False
    return datetime.now(timezone.utc).timestamp() * 1000 - last_seen_ms < 5 * 60 * 1000


def _to_epoch_ms(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        num = float(value)
        if num <= 0:
            return 0
        # 兼容秒/毫秒两种数值时间戳
        return int(num if num > 10_000_000_000 else num * 1000)
    text = str(value).strip()
    if not text:
        return 0
    try:
        num = float(text)
        return int(num if num > 10_000_000_000 else num * 1000)
    except Exception:
        pass
    try:
        normalized = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except Exception:
        return 0


def normalize_device(device: dict = None) -> dict:
    payload = device or {}
    return {
        "device_id": payload.get("device_id", ""),
        "name": payload.get("name", "我的盒子"),
        "public_url": payload.get("public_url", ""),
        "status": "online" if is_online(payload) else payload.get("status", "offline"),
        "last_seen": payload.get("last_seen", 0),
    }


def _require_token_user_id(request: Request) -> str:
    user_id, err = parse_user_from_auth_header(request.headers.get("Authorization", ""))
    if err:
        raise HTTPException(status_code=401, detail=err)
    return str(user_id or "").strip()


async def _fetch_single(db, table: str, filters: dict):
    rows = await db.get(table, filters)
    if isinstance(rows, dict) and rows.get("error"):
        raise HTTPException(status_code=500, detail=f"查询 {table} 失败: {rows['error']}")
    if not rows or isinstance(rows, dict):
        return None
    return rows[0]


async def _require_auth_user(db, request: Request) -> dict:
    user_id = _require_token_user_id(request)
    user = await _fetch_single(db, "users", {"user_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="token 对应用户不存在")
    return user


async def _load_user_devices(db, user_pk: int) -> list:
    bindings = await db.get("device_bindings", {"user_id": user_pk})
    if isinstance(bindings, dict) and bindings.get("error"):
        raise HTTPException(status_code=500, detail=f"查询绑定关系失败: {bindings['error']}")
    if not bindings or isinstance(bindings, dict):
        return []

    devices = []
    visited = set()
    for binding in bindings:
        device_pk = binding.get("device_id")
        if device_pk in visited or device_pk is None:
            continue
        visited.add(device_pk)
        rows = await db.get("devices", {"id": device_pk})
        if isinstance(rows, dict) and rows.get("error"):
            raise HTTPException(status_code=500, detail=f"查询设备失败: {rows['error']}")
        if not rows or isinstance(rows, dict):
            continue
        item = normalize_device(rows[0])
        item["role"] = binding.get("role", "")
        devices.append(item)
    return devices


@router.get("")
async def list_devices(request: Request):
    db = get_db()
    owner = await _require_auth_user(db, request)
    owner_pk = owner.get("id")
    if owner_pk is None:
        return JSONResponse({"success": False, "error": "用户数据异常（缺少主键）"}, status_code=500)

    devices = await _load_user_devices(db, owner_pk)
    return {"success": True, "data": {"devices": devices}}


@router.post("/heartbeat")
async def heartbeat(data: HeartbeatRequest):
    logger.info("[heartbeat] recv device_id=%s", data.device_id)
    db = get_db()
    devices = await db.get("devices", {"device_id": data.device_id})
    if isinstance(devices, dict) and devices.get("error"):
        logger.error("[heartbeat] query devices failed device_id=%s error=%s", data.device_id, devices["error"])
        return JSONResponse({"success": False, "error": f"设备查询失败: {devices['error']}"}, status_code=500)
    existing = devices[0] if devices and not isinstance(devices, dict) else None

    now = datetime.now(timezone.utc)
    update_data = {
        "status": "online",
        # 数据库中 last_seen 为 timestamptz，必须写 ISO 时间字符串
        "last_seen": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    if data.public_url:
        update_data["public_url"] = data.public_url
    if data.firmware_version:
        update_data["firmware_version"] = data.firmware_version
    if data.pairing_code_hash is not None:
        update_data["pairing_code_hash"] = data.pairing_code_hash
    if data.pairing_code_expires is not None:
        update_data["pairing_code_expires"] = datetime.fromtimestamp(data.pairing_code_expires, timezone.utc).isoformat()
    if data.device_secret_hash:
        update_data["device_secret_hash"] = data.device_secret_hash

    if existing:
        patched = await db.patch("devices", {"device_id": data.device_id}, update_data)
        if isinstance(patched, dict) and patched.get("error"):
            logger.error("[heartbeat] patch failed device_id=%s error=%s", data.device_id, patched["error"])
            return JSONResponse({"success": False, "error": f"设备心跳更新失败: {patched['error']}"}, status_code=500)
        logger.info("[heartbeat] patch ok device_id=%s", data.device_id)
    else:
        update_data["device_id"] = data.device_id
        created = await db.post("devices", update_data)
        if isinstance(created, dict) and created.get("error"):
            logger.error("[heartbeat] insert failed device_id=%s error=%s", data.device_id, created["error"])
            return JSONResponse({"success": False, "error": f"设备心跳写入失败: {created['error']}"}, status_code=500)
        logger.info("[heartbeat] insert ok device_id=%s", data.device_id)

    bindings = await db.get("device_bindings", {"device_id": existing["id"]}) if existing else []
    if isinstance(bindings, dict) and bindings.get("error"):
        logger.error("[heartbeat] query bindings failed device_id=%s error=%s", data.device_id, bindings["error"])
        return JSONResponse({"success": False, "error": f"查询设备绑定失败: {bindings['error']}"}, status_code=500)
    claimed = bool(bindings and len(bindings) > 0)

    logger.info("[heartbeat] done device_id=%s claimed=%s", data.device_id, claimed)
    return {"success": True, "claimed": claimed, "message": "ok"}


@router.post("/bind")
async def bind(data: BindRequest, request: Request):
    db = get_db()
    owner = await _require_auth_user(db, request)
    client_ip = request.client.host if request.client else "-"
    owner_user_id = str(owner.get("user_id") or "").strip()
    logger.info(
        "[bind] recv ip=%s user_id=%s device_id=%s pairing_code_len=%s",
        client_ip,
        owner_user_id,
        data.device_id,
        len(data.pairing_code or ""),
    )

    device = await _fetch_single(db, "devices", {"device_id": data.device_id})
    if not device:
        logger.warning("[bind] device not found ip=%s user_id=%s device_id=%s", client_ip, owner_user_id, data.device_id)
        return JSONResponse({"error": "device not found"}, status_code=404)

    if data.pairing_code and device.get("pairing_code_hash"):
        input_hash = hash_sha256(data.pairing_code)
        if input_hash != device.get("pairing_code_hash"):
            logger.warning("[bind] pairing code mismatch user_id=%s device_id=%s", owner_user_id, data.device_id)
            return JSONResponse({"error": "pairing code mismatch"}, status_code=403)

    owner_pk = owner.get("id")
    if owner_pk is None:
        return JSONResponse({"error": "token 对应用户数据异常"}, status_code=500)

    existing_binding = await db.get("device_bindings", {"user_id": owner_pk, "device_id": device["id"]})
    if isinstance(existing_binding, dict) and existing_binding.get("error"):
        logger.error(
            "[bind] query bindings failed user_id=%s device_id=%s error=%s",
            owner_user_id,
            data.device_id,
            existing_binding["error"],
        )
        return JSONResponse({"error": f"查询绑定关系失败: {existing_binding['error']}"}, status_code=500)
    if not existing_binding or isinstance(existing_binding, dict):
        created = await db.post("device_bindings", {"user_id": owner_pk, "device_id": device["id"], "role": "owner"})
        if isinstance(created, dict) and created.get("error"):
            logger.error(
                "[bind] create binding failed user_id=%s device_id=%s error=%s",
                owner_user_id,
                data.device_id,
                created["error"],
            )
            return JSONResponse({"error": f"创建绑定关系失败: {created['error']}"}, status_code=500)
        logger.info("[bind] created user_id=%s device_id=%s", owner_user_id, data.device_id)
    else:
        logger.info("[bind] existed user_id=%s device_id=%s", owner_user_id, data.device_id)

    logger.info("[bind] success user_id=%s device_id=%s", owner_user_id, data.device_id)
    return {"success": True, "claimed": True, "message": "ok", "device": normalize_device(device)}
