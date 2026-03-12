"""
PocketClaw Cloud Service
基于 FastAPI + WebSocket 的设备内网穿透服务
"""
import json
import os
import uuid
import asyncio
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ============== 配置 ==============
PORT = int(os.getenv("PORT", 8764))
DB_FILE = Path(os.getenv("DB_FILE", "data/devices.json"))
DEFAULT_TOKEN = os.getenv("GATEWAY_TOKEN", "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c")

# ============== 数据模型 ==============
class Device(BaseModel):
    device_id: str
    public_url: str = ""
    device_secret_hash: str = ""
    firmware_version: str = "1.0.0"
    version: str = "1.0.0"
    status: str = "offline"
    last_seen: int = 0
    provisioned_at: int = 0
    pairing_code_hash: Optional[str] = None
    pairing_code_expires: Optional[int] = None
    name: str = "我的盒子"

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

# ============== 内存存储 ==============
class DeviceStore:
    def __init__(self):
        self.devices: Dict[str, dict] = {}
        self.bindings: Dict[str, str] = {}
        self.load()
    
    def load(self):
        """从文件加载数据"""
        if DB_FILE.exists():
            try:
                data = json.loads(DB_FILE.read_text())
                self.devices = data.get("devices", {})
                self.bindings = data.get("bindings", {})
            except Exception as e:
                print(f"加载数据失败: {e}")
    
    def save(self):
        """保存数据到文件"""
        DB_FILE.parent.mkdir(parents=True, exist_ok=True)
        DB_FILE.write_text(json.dumps({
            "devices": self.devices,
            "bindings": self.bindings
        }, indent=2))
    
    def get_device(self, device_id: str) -> Optional[dict]:
        return self.devices.get(device_id)
    
    def update_device(self, device_id: str, data: dict):
        existing = self.devices.get(device_id, {})
        self.devices[device_id] = {**existing, **data, "device_id": device_id}
        self.save()
    
    def bind_device(self, device_id: str, user_id: str):
        self.bindings[device_id] = user_id
        self.save()
    
    def unbind_device(self, device_id: str):
        if device_id in self.bindings:
            del self.bindings[device_id]
            self.save()
    
    def is_bound(self, device_id: str) -> bool:
        return device_id in self.bindings
    
    def get_user_id(self, device_id: str) -> Optional[str]:
        return self.bindings.get(device_id)

store = DeviceStore()

# ============== WebSocket 管理 ==============
class ConnectionManager:
    """管理设备 WebSocket 连接"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
    
    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        print(f"设备 {device_id} 已连接")
    
    def disconnect(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]
        print(f"设备 {device_id} 已断开")
    
    async def send_request(self, device_id: str, function: str, params: dict = None) -> dict:
        """发送请求到设备，等待响应"""
        if device_id not in self.active_connections:
            raise HTTPException(status_code=404, detail=f"Device {device_id} not connected")
        
        websocket = self.active_connections[device_id]
        request_id = str(uuid.uuid4())
        
        payload = {
            "request_id": request_id,
            "function": function,
            "params": params or {}
        }
        
        # 创建 Future 等待响应
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_requests[request_id] = future
        
        try:
            await websocket.send_text(json.dumps(payload))
            # 等待 10 秒超时
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
        """处理设备返回的响应"""
        if request_id in self.pending_requests:
            self.pending_requests[request_id].set_result(data)
            del self.pending_requests[request_id]

manager = ConnectionManager()

# ============== FastAPI 应用 ==============
app = FastAPI(title="PocketClaw Cloud Service")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== 辅助函数 ==============
def is_online(device: dict) -> bool:
    """检查设备是否在线（5分钟内有心跳）"""
    if not device:
        return False
    return datetime.now().timestamp() * 1000 - (device.get("last_seen", 0)) < 5 * 60 * 1000

def get_device_view(device_id: str) -> dict:
    """获取设备视图"""
    device = store.get_device(device_id)
    if not device:
        return None
    
    return {
        "device_id": device_id,
        "name": device.get("name", "我的盒子"),
        "public_url": device.get("public_url", ""),
        "device_secret_hash": device.get("device_secret_hash", ""),
        "version": device.get("version", "1.0.0"),
        "firmware_version": device.get("firmware_version", "1.0.0"),
        "status": "online" if is_online(device) else device.get("status", "offline"),
        "last_seen": device.get("last_seen", 0),
        "provisioned_at": device.get("provisioned_at", 0),
        "pairing_code_hash": device.get("pairing_code_hash"),
        "pairing_code_expires": device.get("pairing_code_expires"),
    }

def hash_sha256(data: str) -> str:
    """SHA256 哈希"""
    return hashlib.sha256(data.encode()).hexdigest()

# ============== 设备端接口 ==============

@app.websocket("/proxy/{device_id}")
async def proxy_websocket(websocket: WebSocket, device_id: str):
    """设备 WebSocket 连接"""
    await manager.connect(device_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"收到设备 {device_id} 消息: {data}")
            try:
                response = json.loads(data)
                request_id = response.get("request_id")
                if request_id:
                    await manager.handle_response(request_id, response.get("data"))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(device_id)
    except Exception as e:
        print(f"WebSocket 错误: {e}")
        manager.disconnect(device_id)

# ============== 设备心跳 ==============
@app.post("/v1/device/heartbeat")
async def heartbeat(data: HeartbeatRequest):
    """设备心跳"""
    if not data.device_id:
        return JSONResponse({"error": "device_id required"}, status_code=400)
    
    existing = store.get_device(data.device_id) or {}
    secret_hash = data.device_secret_hash or existing.get("device_secret_hash", "")
    
    store.update_device(data.device_id, {
        "public_url": data.public_url or existing.get("public_url", ""),
        "device_secret_hash": secret_hash,
        "firmware_version": data.firmware_version or existing.get("firmware_version", "1.0.0"),
        "version": data.firmware_version or existing.get("version", "1.0.0"),
        "status": "online",
        "last_seen": int(datetime.now().timestamp() * 1000),
        "pairing_code_hash": data.pairing_code_hash if data.pairing_code_hash is not None else existing.get("pairing_code_hash"),
        "pairing_code_expires": data.pairing_code_expires if data.pairing_code_expires is not None else existing.get("pairing_code_expires"),
    })
    
    is_bound = store.is_bound(data.device_id)
    return {"success": True, "claimed": is_bound, "message": "ok"}

# ============== 设备绑定 ==============
@app.post("/v1/device/bind")
async def bind(data: BindRequest):
    """小程序绑定设备"""
    if not data.device_id or not data.user_id:
        return JSONResponse({"error": "device_id and user_id required"}, status_code=400)
    
    device = store.get_device(data.device_id)
    
    # 验证 pairing_code
    if data.pairing_code and device and device.get("pairing_code_hash"):
        input_hash = hash_sha256(data.pairing_code)
        if input_hash != device.get("pairing_code_hash"):
            return JSONResponse({"error": "pairing code mismatch"}, status_code=403)
        
        if device.get("pairing_code_expires"):
            if datetime.now().timestamp() > device.get("pairing_code_expires"):
                return JSONResponse({"error": "pairing code expired"}, status_code=403)
    
    store.bind_device(data.device_id, data.user_id)
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
    """获取设备状态"""
    device = store.get_device(device_id)
    if not device:
        return JSONResponse({"error": "device not found"}, status_code=404)
    return {"ok": True, "device": get_device_view(device_id)}

@app.get("/device/{device_id}")
async def get_device(device_id: str):
    """获取设备信息"""
    device = store.get_device(device_id)
    if not device:
        return JSONResponse({"error": "device not found"}, status_code=404)
    return get_device_view(device_id)

@app.delete("/device/{device_id}/bind")
async def unbind_device(device_id: str):
    """解绑设备"""
    store.unbind_device(device_id)
    return {"ok": True}

@app.post("/device/{device_id}/gateway/{path:path}")
async def gateway_proxy(device_id: str, path: str, request: Request):
    """网关代理 - 通过云端转发请求到设备"""
    body = await request.body()
    try:
        data = json.loads(body) if body else {}
    except:
        data = {}
    
    # 从请求头获取覆盖值
    gw_url = request.headers.get("X-Gw-Url")
    gw_token = request.headers.get("X-Gw-Token")
    
    # 实际通过 WebSocket 转发到设备
    try:
        result = await manager.send_request(device_id, path, data)
        return result
    except HTTPException:
        # 如果设备不在线，尝试 HTTP 代理（如果提供了 URL）
        if gw_url:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{gw_url}/{path}",
                    json=data,
                    headers={"Authorization": f"Bearer {gw_token}"} if gw_token else {}
                )
                return JSONResponse(resp.json(), status_code=resp.status_code)
        raise

# ============== 系统接口 ==============

@app.get("/proxy/health")
async def health():
    """健康检查"""
    return {"ok": True, "status": "live", "ts": int(datetime.now().timestamp() * 1000)}

@app.get("/proxy/metrics")
async def metrics():
    """系统指标"""
    import psutil
    return {
        "cpu": psutil.cpu_percent(),
        "mem": psutil.virtual_memory().percent,
        "memUsedMB": psutil.virtual_memory().used / 1024 / 1024,
        "memTotalMB": psutil.virtual_memory().total / 1024 / 1024,
        "ts": int(datetime.now().timestamp() * 1000)
    }

# ============== 静态文件服务 ==============
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
