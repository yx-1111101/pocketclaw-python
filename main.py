"""
PocketClaw Cloud Service
基于 FastAPI + WebSocket + MySQL 的设备内网穿透服务
"""
import json
import os
import uuid
import asyncio
import hashlib
import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from app.core.db import MySQLClient

# ============== 配置 ==============
PORT = int(os.getenv("PORT", 8764))
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "openfriday")
DEFAULT_TOKEN = os.getenv("GATEWAY_TOKEN", "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c")

db = MySQLClient(MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB)

# ============== 数据模型 ==============
class HeartbeatRequest(BaseModel):
    device_id: str
    public_url: Optional[str] = None
    pairing_code_hash: Optional[str] = None
    pairing_code_expires: Optional[int] = None
    firmware_version: Optional[str] = None
    timestamp: Optional[int] = None
    device_secret_hash: Optional[str] = None

class BindRequest(BaseModel):
    device_id: str
    user_id: str
    pairing_code: Optional[str] = None

# ============== WebSocket 管理 ==============
class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}
        self.pending_requests: dict = {}
    
    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
    
    def disconnect(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]
    
    async def send_request(self, device_id: str, function: str, params: dict = None):
        if device_id not in self.active_connections:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not connected")
        
        websocket = self.active_connections[device_id]
        request_id = str(uuid.uuid4())
        payload = {"request_id": request_id, "function": function, "params": params or {}}
        
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_requests[request_id] = future
        
        try:
            await websocket.send_text(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=10.0)
            return {"status": "success", "data": result}
        except asyncio.TimeoutError:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            raise HTTPException(status_code=504, detail="Request timeout")
        except Exception as e:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            raise HTTPException(status_code=500, detail=str(e))
    
    async def handle_response(self, request_id: str, data: dict):
        if request_id in self.pending_requests:
            self.pending_requests[request_id].set_result(data)
            del self.pending_requests[request_id]

manager = ConnectionManager()

# ============== FastAPI 应用 ==============
app = FastAPI(title="PocketClaw Cloud Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== 辅助函数 ==============
def is_online(device: dict) -> bool:
    if not device:
        return False
    last_seen = device.get("last_seen")
    if not last_seen:
        return False
    return datetime.now().timestamp() * 1000 - last_seen < 5 * 60 * 1000

def hash_sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()

# ============== 设备 WebSocket ==============
@app.websocket("/proxy/{device_id}")
async def proxy_websocket(websocket: WebSocket, device_id: str):
    await manager.connect(device_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                response = json.loads(data)
                request_id = response.get("request_id")
                if request_id:
                    await manager.handle_response(request_id, response.get("data"))
            except:
                pass
    except WebSocketDisconnect:
        manager.disconnect(device_id)
    except Exception as e:
        manager.disconnect(device_id)

# ============== 设备心跳 ==============
@app.post("/v1/device/heartbeat")
async def heartbeat(data: HeartbeatRequest):
    # 查询设备是否存在
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
    
    # 检查绑定
    bindings = await db.get("device_bindings", {"device_id": existing["id"] if existing else "none"})
    claimed = bool(bindings and len(bindings) > 0)
    
    return {"success": True, "claimed": claimed, "message": "ok"}

# ============== 设备绑定 ==============
@app.post("/v1/device/bind")
async def bind(data: BindRequest):
    # 查找设备
    devices = await db.get("devices", {"device_id": data.device_id})
    if not devices:
        return JSONResponse({"error": "device not found"}, status_code=404)
    
    device = devices[0]
    
    # 验证 pairing_code
    if data.pairing_code and device.get("pairing_code_hash"):
        input_hash = hash_sha256(data.pairing_code)
        if input_hash != device.get("pairing_code_hash"):
            return JSONResponse({"error": "pairing code mismatch"}, status_code=403)
        
        if device.get("pairing_code_expires"):
            expires = device["pairing_code_expires"]
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires).timestamp()
            if datetime.now().timestamp() > expires:
                return JSONResponse({"error": "pairing code expired"}, status_code=403)
    
    # 查找用户
    users = await db.get("users", {"user_id": data.user_id})
    if not users:
        return JSONResponse({"error": "user not found"}, status_code=404)
    
    user = users[0]
    
    # 创建绑定
    await db.post("device_bindings", {
        "user_id": user["id"],
        "device_id": device["id"],
        "role": "owner"
    })
    
    return {"success": True, "claimed": True, "message": "ok"}

# 兼容旧接口
@app.post("/device/heartbeat")
async def heartbeat_legacy(data: HeartbeatRequest):
    return await heartbeat(data)

@app.post("/device/bind")
async def bind_legacy(data: BindRequest):
    return await bind(data)

# ============== 小程序端接口 ==============

@app.get("/device/{device_id}/status")
async def get_status(device_id: str):
    devices = await db.get("devices", {"device_id": device_id})
    if not devices:
        return JSONResponse({"error": "device not found"}, status_code=404)
    device = devices[0]
    return {"ok": True, "device": {
        "device_id": device["device_id"],
        "status": "online" if is_online(device) else device.get("status", "offline"),
        "last_seen": device.get("last_seen", 0)
    }}

@app.get("/device/{device_id}")
async def get_device(device_id: str):
    devices = await db.get("devices", {"device_id": device_id})
    if not devices:
        return JSONResponse({"error": "device not found"}, status_code=404)
    device = devices[0]
    return {
        "device_id": device["device_id"],
        "name": device.get("name", "我的盒子"),
        "public_url": device.get("public_url", ""),
        "status": "online" if is_online(device) else device.get("status", "offline"),
        "last_seen": device.get("last_seen", 0)
    }

@app.delete("/device/{device_id}/bind")
async def unbind_device(device_id: str):
    devices = await db.get("devices", {"device_id": device_id})
    if devices:
        await db.delete("device_bindings", {"device_id": devices[0]["id"]})
    return {"ok": True}

@app.post("/device/{device_id}/gateway/{path:path}")
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

# 复数路径兼容（主路径：/devices/..., 保留 /device/... 以兼容旧客户端）
@app.get("/devices/{device_id}/status")
async def get_status_plural(device_id: str):
    return await get_status(device_id)

@app.get("/devices/{device_id}")
async def get_device_plural(device_id: str):
    return await get_device(device_id)

@app.delete("/devices/{device_id}/bind")
async def unbind_device_plural(device_id: str):
    return await unbind_device(device_id)

@app.post("/devices/{device_id}/gateway/{path:path}")
async def gateway_proxy_plural(device_id: str, path: str, request: Request):
    return await gateway_proxy(device_id, path, request)

# ============== 微信登录 ==============
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "wxc6ee0aee83c794e7")
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "1264e0e7f7a90e65a92061355873bb37")

class WechatLoginRequest(BaseModel):
    code: str

class WechatBindRequest(BaseModel):
    openid: str
    phone: str
    code: str

@app.post("/api/wechat/login")
async def wechat_login(data: WechatLoginRequest):
    # 调用微信 API
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": WECHAT_APP_ID,
        "secret": WECHAT_APP_SECRET,
        "js_code": data.code,
        "grant_type": "authorization_code"
    }
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, params=params)
            result = resp.json()
            
            if "openid" in result:
                openid = result["openid"]
                session_key = result.get("session_key", "")
                
                # 查找或创建用户
                users = await db.get("users", {"openid": openid})
                if users and not isinstance(users, dict):
                    user = users[0]
                    user_id = user["user_id"]
                else:
                    user_id = f"wx_{openid[:16]}"
                    await db.post("users", {
                        "user_id": user_id,
                        "openid": openid
                    })
                
                return {
                    "success": True,
                    "data": {
                        "openid": openid,
                        "user_id": user_id,
                        "session_key": session_key
                    }
                }
            else:
                return {"success": False, "error": result.get("errmsg", "获取 openid 失败")}
        except Exception as e:
            return {"success": False, "error": str(e)}

@app.post("/api/wechat/bind-phone")
async def wechat_bind_phone(data: WechatBindRequest):
    # 验证码验证
    if len(data.code) != 6 or not data.code.isdigit():
        return {"success": False, "error": "验证码错误"}
    
    # 查找用户
    users = await db.get("users", {"openid": data.openid})
    if not users:
        return {"success": False, "error": "用户不存在，请先登录"}
    
    user = users[0]
    await db.patch("users", {"openid": data.openid}, {"phone": data.phone})
    
    return {"success": True}

@app.get("/api/wechat/user/{user_id}")
async def get_wechat_user(user_id: str):
    users = await db.get("users", {"user_id": user_id})
    if not users:
        return JSONResponse({"error": "用户不存在"}, status_code=404)
    user = users[0]
    return {
        "user_id": user["user_id"],
        "openid": user.get("openid", ""),
        "phone": user.get("phone", ""),
        "nickname": user.get("nickname", ""),
        "avatar": user.get("avatar", "")
    }

# ============== 系统接口 ==============

@app.get("/proxy/health")
async def health():
    return {"ok": True, "status": "live", "ts": int(datetime.now().timestamp() * 1000)}

@app.get("/proxy/metrics")
async def metrics():
    try:
        import psutil
        return {
            "cpu": psutil.cpu_percent(),
            "mem": psutil.virtual_memory().percent,
            "ts": int(datetime.now().timestamp() * 1000)
        }
    except:
        return {"cpu": 0, "mem": 0, "ts": int(datetime.now().timestamp() * 1000)}

# ============== 静态文件 ==============
PUBLIC_DIR = Path("public")

@app.get("/")
async def root():
    index_file = PUBLIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "PocketClaw Cloud Service"}

@app.get("/{path:path}")
async def static_files(path: str):
    file_path = PUBLIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return JSONResponse({"error": "Not found"}, status_code=404)

# ============== 启动 ==============
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
