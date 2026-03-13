"""FastAPI 应用入口"""
import json
import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.config import PORT, SUPABASE_URL, SUPABASE_KEY
from app.core.supabase import get_db, init_db
from app.core.websocket import manager
from api import device, wechat, proxy

# 初始化
init_db(SUPABASE_URL, SUPABASE_KEY)
logger = logging.getLogger("uvicorn.error")

# 创建应用
app = FastAPI(title="PocketClaw Cloud Service")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(device.router)
app.include_router(wechat.router)
app.include_router(proxy.router)


async def upsert_device_presence(device_id: str):
    """在设备建立 WS 连接时确保 devices 里存在该 device_id。"""
    logger.info("[ws_presence] start device_id=%s", device_id)
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "status": "online",
        "last_seen": now,
        "updated_at": now,
    }
    rows = await db.get("devices", {"device_id": device_id})
    if isinstance(rows, dict) and rows.get("error"):
        logger.error("[ws_presence] query failed device_id=%s error=%s", device_id, rows["error"])
        return

    if rows and not isinstance(rows, dict):
        patched = await db.patch("devices", {"device_id": device_id}, payload)
        if isinstance(patched, dict) and patched.get("error"):
            logger.error("[ws_presence] patch failed device_id=%s error=%s", device_id, patched["error"])
        else:
            logger.info("[ws_presence] patch ok device_id=%s", device_id)
        return

    created = await db.post("devices", {"device_id": device_id, **payload})
    if isinstance(created, dict) and created.get("error"):
        logger.error("[ws_presence] insert failed device_id=%s error=%s", device_id, created["error"])
    else:
        logger.info("[ws_presence] insert ok device_id=%s", device_id)


# WebSocket
@app.websocket("/stream/{device_id}")
@app.websocket("/proxy/{device_id}")
async def proxy_websocket(websocket: WebSocket, device_id: str):
    client_ip = websocket.client.host if websocket.client else "-"
    logger.info("[ws_proxy] connect ip=%s device_id=%s", client_ip, device_id)
    await manager.connect(device_id, websocket)
    await upsert_device_presence(device_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                response = json.loads(data)
                request_id = response.get("request_id")
                if request_id:
                    await manager.handle_response(request_id, response.get("data"))
            except Exception:
                pass
    except WebSocketDisconnect:
        logger.info("[ws_proxy] disconnect ip=%s device_id=%s", client_ip, device_id)
        manager.disconnect(device_id)
    except Exception:
        logger.exception("[ws_proxy] error ip=%s device_id=%s", client_ip, device_id)
        manager.disconnect(device_id)

# 系统接口
@app.get("/health")
async def health():
    return {"ok": True, "status": "live", "ts": int(datetime.now().timestamp() * 1000)}

@app.get("/metrics")
async def metrics():
    try:
        import psutil
        return {"cpu": psutil.cpu_percent(), "mem": psutil.virtual_memory().percent, "ts": int(datetime.now().timestamp() * 1000)}
    except:
        return {"cpu": 0, "mem": 0, "ts": int(datetime.now().timestamp() * 1000)}

# 静态文件
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
