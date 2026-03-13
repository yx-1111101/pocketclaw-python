"""设备 API 路由"""
from datetime import datetime
from fastapi import APIRouter
from app.core.supabase import get_db
from app.core.security import hash_sha256
from app.models.schemas import HeartbeatRequest, BindRequest

router = APIRouter(prefix="/devices", tags=["设备"])

def is_online(device: dict) -> bool:
    if not device:
        return False
    last_seen = device.get("last_seen")
    if not last_seen:
        return False
    return datetime.now().timestamp() * 1000 - last_seen < 5 * 60 * 1000

@router.post("/heartbeat")
async def heartbeat(data: HeartbeatRequest):
    db = get_db()
    devices = await db.get("devices", {"device_id": data.device_id})
    existing = devices[0] if devices and not isinstance(devices, dict) else None
    
    update_data = {
        "status": "online",
        "last_seen": int(datetime.now().timestamp() * 1000),
        "updated_at": datetime.now().isoformat()
    }
    
    if data.public_url:
        update_data["public_url"] = data.public_url
    if data.firmware_version:
        update_data["firmware_version"] = data.firmware_version
    if data.pairing_code_hash is not None:
        update_data["pairing_code_hash"] = data.pairing_code_hash
    if data.pairing_code_expires is not None:
        update_data["pairing_code_expires"] = datetime.fromtimestamp(data.pairing_code_expires).isoformat()
    if data.device_secret_hash:
        update_data["device_secret_hash"] = data.device_secret_hash
    
    if existing:
        await db.patch("devices", {"device_id": data.device_id}, update_data)
    else:
        update_data["device_id"] = data.device_id
        await db.post("devices", update_data)
    
    bindings = await db.get("device_bindings", {"device_id": existing["id"]}) if existing else []
    claimed = bool(bindings and len(bindings) > 0)
    
    return {"success": True, "claimed": claimed, "message": "ok"}

@router.post("/bind")
async def bind(data: BindRequest):
    db = get_db()
    devices = await db.get("devices", {"device_id": data.device_id})
    if not devices:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "device not found"}, status_code=404)
    
    device = devices[0]
    
    if data.pairing_code and device.get("pairing_code_hash"):
        input_hash = hash_sha256(data.pairing_code)
        if input_hash != device.get("pairing_code_hash"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "pairing code mismatch"}, status_code=403)
    
    users = await db.get("users", {"user_id": data.user_id})
    if not users:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "user not found"}, status_code=404)
    
    user = users[0]
    await db.post("device_bindings", {"user_id": user["id"], "device_id": device["id"], "role": "owner"})
    
    return {"success": True, "claimed": True, "message": "ok"}

