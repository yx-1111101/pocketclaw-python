"""FastAPI 应用入口"""
import json
import logging
import time
import uuid
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.config import PORT, SUPABASE_URL, SUPABASE_KEY
from app.core.security import parse_user_from_auth_header
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


def _truncate_text(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}...(truncated {len(text) - limit} chars)"


def _normalize_payload(raw: bytes) -> str:
    if not raw:
        return ""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return "<binary>"
    return _truncate_text(text)


@app.middleware("http")
async def log_http_io(request: Request, call_next):
    path = request.url.path
    if not (path.startswith("/devices") or path.startswith("/api/auth")):
        return await call_next(request)

    request_id = uuid.uuid4().hex[:8]
    client_ip = request.client.host if request.client else "-"
    started_at = time.perf_counter()
    body = await request.body()

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    wrapped_request = Request(request.scope, receive)
    req_payload = _normalize_payload(body)
    auth = request.headers.get("Authorization", "")

    logger.info(
        "[http_io][%s] IN %s %s ip=%s query=%s auth=%s body=%s",
        request_id,
        request.method,
        path,
        client_ip,
        request.url.query or "",
        auth or "-",
        req_payload or "-",
    )

    try:
        response = await call_next(wrapped_request)
    except Exception:
        logger.exception("[http_io][%s] EX %s %s ip=%s", request_id, request.method, path, client_ip)
        raise

    cost_ms = int((time.perf_counter() - started_at) * 1000)
    resp_body = getattr(response, "body", b"")
    if isinstance(resp_body, bytes):
        resp_payload = _normalize_payload(resp_body)
    else:
        resp_payload = _truncate_text(str(resp_body))

    logger.info(
        "[http_io][%s] OUT %s %s status=%s cost=%sms body=%s",
        request_id,
        request.method,
        path,
        response.status_code,
        cost_ms,
        resp_payload or "<streaming or empty>",
    )
    return response


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
                else:
                    logger.info(
                        "[ws_proxy] message without request_id device_id=%s keys=%s",
                        device_id,
                        list(response.keys()) if isinstance(response, dict) else [],
                    )
            except Exception:
                logger.warning("[ws_proxy] message parse failed device_id=%s raw=%s", device_id, data[:300])
    except WebSocketDisconnect:
        logger.info("[ws_proxy] disconnect ip=%s device_id=%s", client_ip, device_id)
        manager.disconnect(device_id)
    except Exception:
        logger.exception("[ws_proxy] error ip=%s device_id=%s", client_ip, device_id)
        manager.disconnect(device_id)

# ── 小程序 WebSocket 接入 ────────────────────────────────
@app.websocket("/ws/miniapp/{device_id}")
async def miniapp_websocket(websocket: WebSocket, device_id: str):
    """小程序连接此端点，后端将消息中继到设备 Gateway"""
    client_ip = websocket.client.host if websocket.client else "-"
    logger.info("[ws_miniapp] connect ip=%s device_id=%s", client_ip, device_id)
    
    await websocket.accept()
    manager.connect_client(device_id, websocket)

    # 通知小程序连接成功
    await websocket.send_text(json.dumps({
        "type": "connected",
        "device_id": device_id,
        "device_online": device_id in manager.active_connections,
    }))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "error": "invalid json"}))
                continue

            msg_type = msg.get("type", "")

            # ── 聊天消息 ──────────────────────────────────
            if msg_type == "chat":
                if device_id not in manager.active_connections:
                    await websocket.send_text(json.dumps({
                        "type": "error", "error": "device not connected"
                    }))
                    continue

                # 向设备发送 chat.send 请求
                try:
                    result = await manager.send_request(device_id, "v1/chat/completions", {
                        "messages": msg.get("messages", []),
                        "model": msg.get("model", "default"),
                        "stream": False,
                    })
                    await websocket.send_text(json.dumps({
                        "type": "chat_reply",
                        "data": result.get("data"),
                    }))
                except Exception as e:
                    await websocket.send_text(json.dumps({
                        "type": "error", "error": str(e)
                    }))

            # ── ping ──────────────────────────────────────
            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            # ── 设备状态查询 ──────────────────────────────
            elif msg_type == "device_status":
                await websocket.send_text(json.dumps({
                    "type": "device_status",
                    "online": device_id in manager.active_connections,
                }))

            else:
                await websocket.send_text(json.dumps({
                    "type": "error", "error": f"unknown type: {msg_type}"
                }))

    except WebSocketDisconnect:
        logger.info("[ws_miniapp] disconnect ip=%s device_id=%s", client_ip, device_id)
    except Exception:
        logger.exception("[ws_miniapp] error ip=%s device_id=%s", client_ip, device_id)
    finally:
        manager.disconnect_client(device_id)


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


@app.get("/debug/ws-connections")
async def debug_ws_connections(request: Request, device_id: str = ""):
    """调试接口：查看当前内存中的 WebSocket 在线设备。"""
    user_id, err = parse_user_from_auth_header(request.headers.get("Authorization", ""))
    if err:
        return JSONResponse({"success": False, "error": err}, status_code=401)

    items = []
    for did, ws in manager.active_connections.items():
        client_ip = "-"
        try:
            client_ip = ws.client.host if ws.client else "-"
        except Exception:
            pass
        items.append({"device_id": did, "client_ip": client_ip})

    items.sort(key=lambda item: item["device_id"])
    target = str(device_id or "").strip()
    if target:
        matched = [item for item in items if item["device_id"] == target]
        return {
            "success": True,
            "viewer_user_id": user_id,
            "total": len(items),
            "device_id": target,
            "connected": bool(matched),
            "connections": matched,
        }

    return {
        "success": True,
        "viewer_user_id": user_id,
        "total": len(items),
        "connections": items,
    }

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
