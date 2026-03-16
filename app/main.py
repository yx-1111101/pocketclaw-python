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
from api import device, wechat, proxy, cron, skills, sessions

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
app.include_router(cron.router)
app.include_router(skills.router)
app.include_router(sessions.router)


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

# ── 文件上传 ─────────────────────────────────────────────────────────────────
import shutil, mimetypes
from fastapi import UploadFile, File as FastFile
from fastapi.responses import FileResponse as FResp

UPLOAD_DIR = Path("/tmp/pocketclaw_uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@app.post("/system/upload")
async def upload_file(file: UploadFile = FastFile(...)):
    suffix = Path(file.filename or "file").suffix or ""
    unique_name = f"{uuid.uuid4()}{suffix}"
    dest = UPLOAD_DIR / unique_name
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    size = dest.stat().st_size
    mime = mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    return {"success": True, "url": f"/system/files/{unique_name}", "name": file.filename, "size": size, "mime": mime}

@app.get("/system/files/{filename}")
async def get_file(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "not found"})
    return FResp(path)

# ── 静态文件（必须放最后）────────────────────────────────────────────────────
@app.get("/{path:path}")
async def static_files(path: str):
    file_path = PUBLIC_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    return JSONResponse({"error": "Not found"}, status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
