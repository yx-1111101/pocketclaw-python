"""FastAPI 应用入口"""
import json
import uuid
from pathlib import Path
from typing import Dict, Set
from datetime import datetime

from fastapi import FastAPI, WebSocket as FWS, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import PORT, REDIS_HOST, REDIS_PORT, REDIS_DB, SUPABASE_URL, SUPABASE_KEY
from app.core.supabase import init_db
from app.core.redis_cache import init_cache
from app.core.websocket import manager
from api import device, wechat, proxy

# 初始化 Supabase（持久化存储）和 Redis（缓存）
init_db(SUPABASE_URL, SUPABASE_KEY)
init_cache(REDIS_HOST, REDIS_PORT, REDIS_DB)

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

# 流式客户端管理：device_id → set of client WebSockets
stream_clients: Dict[str, Set[FWS]] = {}


# 设备端反向代理 WebSocket
@app.websocket("/proxy/{device_id}")
async def proxy_websocket(websocket: FWS, device_id: str):
    await manager.connect(device_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                response = json.loads(data)
            except Exception:
                continue

            request_id = response.get("request_id")

            # 流式事件：透传给订阅该设备的所有客户端
            if "stream_event" in response:
                clients = stream_clients.get(device_id, set())
                msg = json.dumps({
                    "type": "stream",
                    "request_id": request_id,
                    "event": response["stream_event"],
                })
                dead = []
                for client_ws in clients:
                    try:
                        await client_ws.send_text(msg)
                    except Exception:
                        dead.append(client_ws)
                for d in dead:
                    clients.discard(d)
                continue

            # 普通 RPC 响应
            if request_id:
                resp_data = response.get("data", {})
                if isinstance(resp_data, dict) and resp_data.get("done"):
                    clients = stream_clients.get(device_id, set())
                    msg = json.dumps({
                        "type": "stream_end",
                        "request_id": request_id,
                        "data": resp_data,
                    })
                    dead = []
                    for client_ws in clients:
                        try:
                            await client_ws.send_text(msg)
                        except Exception:
                            dead.append(client_ws)
                    for d in dead:
                        clients.discard(d)

                await manager.handle_response(request_id, resp_data)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(device_id)


# 客户端流式 WebSocket
@app.websocket("/stream/{device_id}")
async def stream_websocket(websocket: FWS, device_id: str):
    """小程序/客户端通过此端点接收实时流式事件。"""
    await websocket.accept()

    if device_id not in stream_clients:
        stream_clients[device_id] = set()
    stream_clients[device_id].add(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            action = msg.get("action")

            if action == "chat":
                message = msg.get("message", "")
                session_key = msg.get("sessionKey", f"agent:main:stream-{uuid.uuid4().hex[:8]}")

                if not manager.is_connected(device_id):
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "error": "Device not connected",
                    }))
                    continue

                try:
                    result = await manager.send_request(
                        device_id,
                        "v1/chat/completions",
                        {
                            "messages": [{"role": "user", "content": message}],
                            "sessionKey": session_key,
                            "_stream": True,
                        },
                        method="POST",
                        timeout=180.0,
                    )
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "error": str(e),
                    }))
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        stream_clients.get(device_id, set()).discard(websocket)
        if device_id in stream_clients and not stream_clients[device_id]:
            del stream_clients[device_id]


# 系统接口
@app.get("/health")
async def health():
    return {"ok": True, "status": "live", "ts": int(datetime.now().timestamp() * 1000)}


@app.get("/metrics")
async def metrics():
    try:
        import psutil
        return {"cpu": psutil.cpu_percent(), "mem": psutil.virtual_memory().percent, "ts": int(datetime.now().timestamp() * 1000)}
    except Exception:
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
