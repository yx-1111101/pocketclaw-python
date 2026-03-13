"""网关代理 API 路由"""
from fastapi import APIRouter, HTTPException, Request
import json
from app.core.redis_db import get_db
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
    ws_online = manager.is_connected(device_id)
    return {
        "ok": True,
        "device": {
            "device_id": device["device_id"],
            "status": "online" if (is_online(device) or ws_online) else device.get("status", "offline"),
            "ws_connected": ws_online,
            "last_seen": device.get("last_seen", 0),
        },
    }

@router.get("/{device_id}")
async def get_device(device_id: str):
    db = get_db()
    devices = await db.get("devices", {"device_id": device_id})
    if not devices:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "device not found"}, status_code=404)
    device = devices[0]
    ws_online = manager.is_connected(device_id)
    return {"device_id": device["device_id"], "name": device.get("name", "我的盒子"), "public_url": device.get("public_url", ""), "status": "online" if (is_online(device) or ws_online) else device.get("status", "offline"), "last_seen": device.get("last_seen", 0)}

@router.delete("/{device_id}/bind")
async def unbind_device(device_id: str):
    db = get_db()
    devices = await db.get("devices", {"device_id": device_id})
    if devices:
        await db.delete("device_bindings", {"device_id": devices[0]["id"]})
    return {"ok": True}

@router.get("/{device_id}/metrics")
async def get_device_metrics(device_id: str):
    """通过反向代理获取设备指标（若设备在线）"""
    if manager.is_connected(device_id):
        try:
            result = await manager.send_request(
                device_id, "setup/api/services", method="GET", timeout=10.0,
            )
            return result.get("data", {"cpu": 0, "memory": 0, "uptime": 0})
        except Exception:
            pass
    return {"cpu": 0, "memory": 0, "uptime": 0}


async def _gateway_proxy_impl(device_id: str, path: str, request: Request):
    """通用网关代理：支持 GET/POST/PUT/DELETE，将 HTTP method 透传给设备端。"""
    method = request.method
    body = await request.body()
    try:
        data = json.loads(body) if body else {}
    except Exception:
        data = {}

    query_params = dict(request.query_params) if request.query_params else None

    try:
        result = await manager.send_request(
            device_id, path, data,
            method=method,
            query=query_params,
        )
        return result
    except HTTPException:
        raise


@router.get("/{device_id}/gateway/{path:path}")
async def gateway_proxy_get(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.post("/{device_id}/gateway/{path:path}")
async def gateway_proxy_post(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.put("/{device_id}/gateway/{path:path}")
async def gateway_proxy_put(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.delete("/{device_id}/gateway/{path:path}")
async def gateway_proxy_delete(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)
