"""网关代理 API 路由"""
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.security import parse_user_from_auth_header
from app.core.supabase import get_db
from app.core.websocket import manager

router = APIRouter(prefix="/devices", tags=["网关"])


def is_online(device: dict) -> bool:
    if not device:
        return False
    last_seen = device.get("last_seen")
    if not last_seen:
        return False
    return datetime.now().timestamp() * 1000 - last_seen < 5 * 60 * 1000


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


async def _find_device_by_identity(db, identity: str):
    key = str(identity or "").strip()
    if not key:
        return None
    device = await _fetch_single(db, "devices", {"device_id": key})
    if device:
        return device
    return await _fetch_single(db, "devices", {"box_id": key})


async def _require_user(db, request: Request):
    user_id = _require_token_user_id(request)
    user = await _fetch_single(db, "users", {"user_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="token 对应用户不存在")
    return user


async def _require_user_device(db, request: Request, device_id: str):
    user = await _require_user(db, request)
    device = await _find_device_by_identity(db, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="device not found")

    owner_pk = user.get("id")
    if owner_pk is None:
        raise HTTPException(status_code=500, detail="用户数据异常（缺少主键）")

    binding = await _fetch_single(db, "device_bindings", {"user_id": owner_pk, "device_id": device.get("id")})
    if not binding:
        raise HTTPException(status_code=403, detail="无权访问该设备")
    return user, device, binding


@router.get("/{device_id}/status")
async def get_status(device_id: str, request: Request):
    db = get_db()
    _, device, _ = await _require_user_device(db, request, device_id)
    identity = device.get("device_id") or device.get("box_id") or ""
    return {
        "ok": True,
        "device": {
            "device_id": identity,
            "status": "online" if is_online(device) else device.get("status", "offline"),
            "last_seen": device.get("last_seen", 0),
        },
    }


@router.get("/{device_id}")
async def get_device(device_id: str, request: Request):
    db = get_db()
    _, device, _ = await _require_user_device(db, request, device_id)
    identity = device.get("device_id") or device.get("box_id") or ""
    return {
        "device_id": identity,
        "name": device.get("name", "我的盒子"),
        "public_url": device.get("public_url", ""),
        "status": "online" if is_online(device) else device.get("status", "offline"),
        "last_seen": device.get("last_seen", 0),
    }


@router.delete("/{device_id}/bind")
async def unbind_device(device_id: str, request: Request):
    db = get_db()
    user, device, _ = await _require_user_device(db, request, device_id)
    deleted = await db.delete("device_bindings", {"user_id": user["id"], "device_id": device["id"]})
    if isinstance(deleted, dict) and deleted.get("error"):
        return JSONResponse({"ok": False, "error": f"解绑失败: {deleted['error']}"}, status_code=500)
    return {"ok": True}


@router.get("/{device_id}/metrics")
async def get_device_metrics(device_id: str, request: Request):
    db = get_db()
    await _require_user_device(db, request, device_id)
    return {"cpu": 0, "memory": 0, "uptime": 0}


@router.post("/{device_id}/gateway/{path:path}")
async def gateway_proxy(device_id: str, path: str, request: Request):
    db = get_db()
    await _require_user_device(db, request, device_id)

    body = await request.body()
    try:
        data = json.loads(body) if body else {}
    except Exception:
        data = {}
    try:
        return await manager.send_request(device_id, path, data)
    except HTTPException:
        raise
