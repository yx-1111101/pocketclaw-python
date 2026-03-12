"""网关代理 API 路由"""
from fastapi import APIRouter, HTTPException, Request
import json
from app.core.supabase import get_db
from app.core.websocket import manager

router = APIRouter(prefix="/device", tags=["网关"])

def is_online(device: dict) -> bool:
    from datetime import datetime
    if not device:
        return False
    last_seen = device.get("last_seen")
    if not last_seen:
        return False
    return datetime.now().timestamp() * 1000 - last_seen < 5 * 60 * 1000

@router.get("/{device_id}/status")
async def get_status(device_id: str):
    db = get_db()
    devices = await db.get("devices", {"device_id": device_id})
    if not devices:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "device not found"}, status_code=404)
    device = devices[0]
    return {"ok": True, "device": {"device_id": device["device_id"], "status": "online" if is_online(device) else device.get("status", "offline"), "last_seen": device.get("last_seen", 0)}}

@router.get("/{device_id}")
async def get_device(device_id: str):
    db = get_db()
    devices = await db.get("devices", {"device_id": device_id})
    if not devices:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "device not found"}, status_code=404)
    device = devices[0]
    return {"device_id": device["device_id"], "name": device.get("name", "我的盒子"), "public_url": device.get("public_url", ""), "status": "online" if is_online(device) else device.get("status", "offline"), "last_seen": device.get("last_seen", 0)}

@router.delete("/{device_id}/bind")
async def unbind_device(device_id: str):
    db = get_db()
    devices = await db.get("devices", {"device_id": device_id})
    if devices:
        await db.delete("device_bindings", {"device_id": devices[0]["id"]})
    return {"ok": True}

@router.post("/{device_id}/gateway/{path:path}")
async def gateway_proxy(device_id: str, path: str, request: Request):
    body = await request.body()
    try:
        data = json.loads(body) if body else {}
    except:
        data = {}
    try:
        result = await manager.send_request(device_id, path, data)
        return result
    except HTTPException:
        raise
