"""FastAPI 应用入口"""
import json
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from app.config import PORT, SUPABASE_URL, SUPABASE_KEY
from app.core.supabase import init_db
from app.core.websocket import manager
from api import device, wechat, proxy

# 初始化
init_db(SUPABASE_URL, SUPABASE_KEY)

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

# WebSocket
@app.websocket("/proxy/{device_id}")
async def proxy_websocket(websocket, device_id: str):
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
    except Exception:
        manager.disconnect(device_id)

# 系统接口
@app.get("/proxy/health")
async def health():
    return {"ok": True, "status": "live", "ts": int(datetime.now().timestamp() * 1000)}

@app.get("/proxy/metrics")
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
