"""FastAPI 应用入口"""
import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Set
from fastapi import FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi import WebSocket as FWS
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from app.config import PORT, REDIS_HOST, REDIS_PORT, REDIS_DB, SUPABASE_URL, SUPABASE_KEY
from app.core.security import parse_auth_token, parse_user_from_auth_header
from app.core.supabase import get_db, init_db
from app.core.redis_cache import init_cache
from app.core.websocket import manager
from api import device, wechat, proxy, cron, skills, sessions, models, channels, mcp, tools, usage, billing

# 初始化 Supabase（持久化存储）和 Redis（缓存）
init_db(SUPABASE_URL, SUPABASE_KEY)
init_cache(REDIS_HOST, REDIS_PORT, REDIS_DB)
logger = logging.getLogger("uvicorn.error")
STRICT_STREAM_ROUTING = os.getenv("STRICT_STREAM_ROUTING", "1").strip().lower() not in ("0", "false", "no")

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
app.include_router(models.router)
app.include_router(channels.router)
app.include_router(channels.device_router)
app.include_router(mcp.router)
app.include_router(tools.router)
app.include_router(tools.acp_router)
app.include_router(usage.router)
app.include_router(billing.router)


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


# 流式客户端管理
# - stream_clients: 设备维度在线客户端
# - stream_client_sessions: 客户端声明过的会话订阅（来自 chat.send sessionKey）
# - stream_run_subscribers: runId 绑定到具体客户端，后续 agent 事件按 runId 定向
# - stream_pending_clients: 无 run/session 的早期事件，优先路由到最近发起 chat 的客户端
stream_clients: Dict[str, Set[FWS]] = {}
stream_client_sessions: Dict[str, Dict[FWS, Set[str]]] = {}
stream_run_subscribers: Dict[str, Dict[str, Set[FWS]]] = {}
stream_run_sessions: Dict[str, Dict[str, str]] = {}
stream_pending_clients: Dict[str, Dict[FWS, float]] = {}


def _register_stream_client(device_id: str, websocket: FWS):
    stream_clients.setdefault(device_id, set()).add(websocket)
    stream_client_sessions.setdefault(device_id, {}).setdefault(websocket, set())
    stream_pending_clients.setdefault(device_id, {})


def _unregister_stream_client(device_id: str, websocket: FWS):
    clients = stream_clients.get(device_id)
    if clients:
        clients.discard(websocket)
        if not clients:
            stream_clients.pop(device_id, None)

    session_map = stream_client_sessions.get(device_id)
    if session_map:
        session_map.pop(websocket, None)
        if not session_map:
            stream_client_sessions.pop(device_id, None)

    pending_map = stream_pending_clients.get(device_id)
    if pending_map:
        pending_map.pop(websocket, None)
        if not pending_map:
            stream_pending_clients.pop(device_id, None)

    run_map = stream_run_subscribers.get(device_id)
    if run_map:
        empty_runs = []
        for run_id, ws_set in run_map.items():
            ws_set.discard(websocket)
            if not ws_set:
                empty_runs.append(run_id)
        for run_id in empty_runs:
            run_map.pop(run_id, None)
        if not run_map:
            stream_run_subscribers.pop(device_id, None)

    run_session_map = stream_run_sessions.get(device_id)
    if run_session_map and device_id not in stream_run_subscribers:
        stream_run_sessions.pop(device_id, None)


def _bind_client_session(device_id: str, websocket: FWS, session_key: str):
    if not session_key:
        return
    session_map = stream_client_sessions.setdefault(device_id, {})
    session_map.setdefault(websocket, set()).add(session_key)


def _mark_client_pending(device_id: str, websocket: FWS, ttl_seconds: int = 45):
    now = time.time()
    pending_map = stream_pending_clients.setdefault(device_id, {})
    pending_map[websocket] = now + ttl_seconds
    # 惰性清理过期项
    expired = [ws for ws, exp in pending_map.items() if exp <= now]
    for ws in expired:
        pending_map.pop(ws, None)


def _bind_run_clients(device_id: str, run_id: str, clients: Set[FWS], session_key: str = ""):
    if not run_id or not clients:
        return
    run_map = stream_run_subscribers.setdefault(device_id, {})
    run_map.setdefault(run_id, set()).update(clients)
    if session_key:
        stream_run_sessions.setdefault(device_id, {})[run_id] = session_key


def _resolve_stream_targets(device_id: str, event_name: str, payload: dict) -> Set[FWS]:
    online = set(stream_clients.get(device_id, set()))
    if not online:
        return set()

    p = payload if isinstance(payload, dict) else {}
    run_id = str(p.get("runId") or p.get("run_id") or p.get("request_id") or "").strip()
    session_key = str(p.get("sessionKey") or p.get("session_key") or "").strip()

    # 1) runId 绑定优先
    run_map = stream_run_subscribers.get(device_id, {})
    if run_id and run_id in run_map:
        targets = set(run_map.get(run_id, set())) & online
        if targets:
            return targets

    # 2) sessionKey 路由
    if session_key:
        session_map = stream_client_sessions.get(device_id, {})
        targets = {ws for ws in online if session_key in session_map.get(ws, set())}
        if targets:
            if run_id:
                _bind_run_clients(device_id, run_id, targets, session_key=session_key)
            return targets

    # 3) runId -> sessionKey 回查
    if run_id:
        run_session = stream_run_sessions.get(device_id, {}).get(run_id, "")
        if run_session:
            session_map = stream_client_sessions.get(device_id, {})
            targets = {ws for ws in online if run_session in session_map.get(ws, set())}
            if targets:
                _bind_run_clients(device_id, run_id, targets, session_key=run_session)
                return targets

    # 4) 严格模式：不做“多客户端猜测”路由。
    # 但允许 runId 首次出现时，在“唯一 pending 客户端”下建立确定性绑定。
    pending_map = stream_pending_clients.get(device_id, {})
    now = time.time()
    pending_targets = {ws for ws, exp in pending_map.items() if exp > now and ws in online}
    if STRICT_STREAM_ROUTING:
        if run_id and len(pending_targets) == 1:
            only = set(pending_targets)
            _bind_run_clients(device_id, run_id, only, session_key=session_key)
            logger.info(
                "[ws_stream] bind run_id by unique pending device_id=%s event=%s run_id=%s",
                device_id, event_name, run_id,
            )
            return only
        # 兜底：严格模式下若只有 1 个客户端在线，仍允许投递（避免上游漏带 sessionKey/runId 导致“全程无流”）
        if len(online) == 1:
            only = set(online)
            if run_id:
                _bind_run_clients(device_id, run_id, only, session_key=session_key)
            return only
    else:
        if pending_targets:
            selected = max(pending_targets, key=lambda ws: pending_map.get(ws, 0.0))
            only = {selected}
            if run_id:
                _bind_run_clients(device_id, run_id, only)
            logger.info(
                "[ws_stream] route pending device_id=%s event=%s run_id=%s online=%s pending=%s",
                device_id, event_name, run_id or "-", len(online), len(pending_targets),
            )
            return only

        if len(online) == 1:
            only = set(online)
            if run_id:
                _bind_run_clients(device_id, run_id, only, session_key=session_key)
            return only

    logger.info(
        "[ws_stream] drop unroutable event(strict=%s) device_id=%s event=%s run_id=%s session_key=%s online=%s",
        STRICT_STREAM_ROUTING, device_id, event_name, run_id or "-", session_key or "-", len(online),
    )
    return set()


async def _broadcast_stream_clients(device_id: str, message: dict, targets: Set[FWS] | None = None):
    clients = set(targets or set()) if targets is not None else set(stream_clients.get(device_id, set()))
    if not clients:
        return
    raw = json.dumps(message, ensure_ascii=False)
    dead = []
    # 遍历快照，避免连接增删导致 "Set changed size during iteration"
    for client_ws in tuple(clients):
        try:
            await client_ws.send_text(raw)
        except Exception:
            dead.append(client_ws)
    for d in dead:
        _unregister_stream_client(device_id, d)


def _extract_message_text(message: Any) -> str:
    """从 Gateway/OpenAI 风格 message 中提取纯文本。"""
    if isinstance(message, str):
        return message
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            # 常见结构：{"type":"text","text":"..."}
            text_val = part.get("text")
            if isinstance(text_val, str):
                parts.append(text_val)
                continue
            # 兼容嵌套结构：{"text":{"value":"..."}}
            if isinstance(text_val, dict):
                nested = text_val.get("value")
                if isinstance(nested, str):
                    parts.append(nested)
        return "".join(parts)
    return ""


def _convert_gateway_event(event_name: str, payload: dict) -> List[dict]:
    """将 Gateway 的 event/payload 统一转成小程序 stream 协议。"""
    p = payload if isinstance(payload, dict) else {}
    run_id = p.get("runId") or p.get("run_id") or p.get("request_id") or ""
    out: List[dict] = []

    if event_name == "agent":
        stream = p.get("stream") or p.get("type") or ""
        data = p.get("data") or {}
        phase = p.get("phase") or (data.get("phase") if isinstance(data, dict) else None)
        if stream == "error":
            out.append({
                "type": "error",
                "request_id": run_id,
                "error": (data.get("message") if isinstance(data, dict) else None) or p.get("errorMessage") or "gateway error",
            })
            return out
        if stream == "lifecycle" and phase in ("error", "failed"):
            out.append({
                "type": "error",
                "request_id": run_id,
                "error": (
                    (data.get("error") if isinstance(data, dict) else None)
                    or (data.get("message") if isinstance(data, dict) else None)
                    or p.get("errorMessage")
                    or "agent lifecycle error"
                ),
            })
            return out
        if stream == "lifecycle" and phase == "end":
            out.append({
                "type": "stream_end",
                "request_id": run_id,
                "data": {
                    "content": (data.get("text") if isinstance(data, dict) else "") or "",
                    "toolCalls": (data.get("tool_calls") if isinstance(data, dict) and isinstance(data.get("tool_calls"), list) else []),
                },
            })
            return out
        if stream:
            out.append({
                "type": "stream",
                "request_id": run_id,
                "event": {"type": stream, "data": data if isinstance(data, dict) else {}},
            })
            return out

    if event_name == "chat":
        state = str(p.get("state") or "").lower()
        if state == "error":
            out.append({
                "type": "error",
                "request_id": run_id,
                "error": p.get("errorMessage") or "chat error",
            })
            return out

        # 兼容多种增量格式：
        # 1) {"state":"streaming","delta":"..."}
        # 2) {"state":"delta","message":{"content":[{"type":"text","text":"..."}]}}
        if state in ("streaming", "delta", "stream"):
            delta_text = p.get("delta")
            if not isinstance(delta_text, str) or not delta_text:
                delta_text = _extract_message_text(p.get("message"))
            if not delta_text and isinstance(p.get("content"), (dict, str, list)):
                delta_text = _extract_message_text({"content": p.get("content")})
            if not delta_text:
                return out
            out.append({
                "type": "stream",
                "request_id": run_id,
                "event": {"type": "text", "data": {"delta": delta_text}},
            })
            return out

        if state in ("final", "done", "completed", "complete"):
            final_text = (
                p.get("text")
                or (p.get("content") if isinstance(p.get("content"), str) else "")
                or _extract_message_text(p.get("message"))
            )
            out.append({
                "type": "stream_end",
                "request_id": run_id,
                "data": {
                    "content": final_text or "",
                    "toolCalls": p.get("tool_calls") if isinstance(p.get("tool_calls"), list) else [],
                },
            })
            return out

    return out


def _extract_chat_text(payload: Any) -> str:
    """尽量从常见返回结构中提取最终文本。"""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return ""

    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text

    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        joined = _extract_message_text({"content": content})
        if joined.strip():
            return joined

    from_message = _extract_message_text(payload.get("message"))
    if from_message.strip():
        return from_message

    legacy = payload.get("message")
    if isinstance(legacy, str) and legacy.strip():
        return legacy

    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] if isinstance(choices[0], dict) else {}
        msg = first.get("message") if isinstance(first, dict) else {}
        if isinstance(msg, dict):
            c = msg.get("content")
            if isinstance(c, str) and c.strip():
                return c
    return ""


# 设备端反向代理 WebSocket
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
            except Exception:
                logger.warning("[ws_proxy] message parse failed device_id=%s raw=%s", device_id, data[:300])
                continue

            request_id = response.get("request_id")

            # 流式事件：按 run/session 定向推送（不再设备级广播）
            if "stream_event" in response:
                route_payload = {"request_id": request_id}
                se = response.get("stream_event")
                if isinstance(se, dict):
                    route_payload["runId"] = se.get("runId") or se.get("run_id") or se.get("request_id")
                    route_payload["sessionKey"] = se.get("sessionKey") or se.get("session_key")
                targets = _resolve_stream_targets(device_id, "stream_event", route_payload)
                await _broadcast_stream_clients(device_id, {
                    "type": "stream",
                    "request_id": request_id,
                    "event": response["stream_event"],
                }, targets=targets)
                continue

            # 新版 OpenClaw Gateway event：agent/chat
            event_name = response.get("event") if isinstance(response, dict) else None
            if event_name in ("agent", "chat"):
                payload = response.get("payload") or {}
                converted = _convert_gateway_event(event_name, payload if isinstance(payload, dict) else {})
                targets = _resolve_stream_targets(
                    device_id,
                    event_name,
                    payload if isinstance(payload, dict) else {},
                )
                for msg in converted:
                    await _broadcast_stream_clients(device_id, msg, targets=targets)
                if converted:
                    continue

            # 普通 RPC 响应
            if request_id:
                resp_data = response.get("data", {})
                if isinstance(resp_data, dict):
                    logger.info(
                        "[ws_proxy] rpc response device_id=%s request_id=%s keys=%s data_keys=%s",
                        device_id,
                        request_id,
                        list(response.keys()),
                        list(resp_data.keys()),
                    )
                else:
                    logger.info(
                        "[ws_proxy] rpc response device_id=%s request_id=%s keys=%s data_type=%s",
                        device_id,
                        request_id,
                        list(response.keys()) if isinstance(response, dict) else [],
                        type(resp_data).__name__,
                    )
                # 不再按设备广播 done 响应，避免同设备多会话串流/重复回复
                await manager.handle_response(request_id, resp_data)
            else:
                logger.info(
                    "[ws_proxy] message without request_id device_id=%s keys=%s",
                    device_id,
                    list(response.keys()) if isinstance(response, dict) else [],
                )
    except WebSocketDisconnect:
        logger.info("[ws_proxy] disconnect ip=%s device_id=%s", client_ip, device_id)
    except Exception:
        logger.exception("[ws_proxy] error ip=%s device_id=%s", client_ip, device_id)
    finally:
        manager.disconnect(device_id)


# 客户端流式 WebSocket
@app.websocket("/stream/{device_id}")
async def stream_websocket(
    websocket: FWS,
    device_id: str,
    token: str = Query(default=""),
):
    """
    小程序/客户端通过此端点接收实时流式事件。

    连接时须在 query 参数中带上 token：
      wss://host/stream/{device_id}?token=<Bearer token>

    客户端发送：
      {"action": "chat", "message": "...", "sessionKey": "agent:main:main"}
      {"action": "ping"}

    服务端推送：
      {"type": "stream",     "request_id": "...", "event": {"type": "text", "data": {"delta": "..."}}}
      {"type": "stream_end", "request_id": "...", "data": {"content": "...", "done": true}}
      {"type": "auth_error", "error": "..."}
      {"type": "error",      "error": "..."}
      {"type": "pong"}
    """
    await websocket.accept()

    # ── 鉴权 ──────────────────────────────────────────────────
    if not token:
        await websocket.send_text(json.dumps({"type": "auth_error", "error": "缺少 token"}))
        await websocket.close(code=4001)
        return

    try:
        payload = parse_auth_token(token)
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("token 缺少用户标识")
    except Exception as e:
        await websocket.send_text(json.dumps({"type": "auth_error", "error": str(e)}))
        await websocket.close(code=4001)
        return

    # 校验用户是否绑定了该设备
    db = get_db()
    bindings = await db.get("device_bindings", {"user_id": user_id, "device_id": device_id})
    if not bindings or (isinstance(bindings, dict) and bindings.get("error")):
        await websocket.send_text(json.dumps({"type": "auth_error", "error": "无权访问该设备"}))
        await websocket.close(code=4003)
        return

    logger.info("[ws_stream] authed user_id=%s device_id=%s", user_id, device_id)
    # ── 鉴权结束 ───────────────────────────────────────────────

    _register_stream_client(device_id, websocket)

    # sessionKey 稳定默认值：agent:main:{user_id}（每个用户独立，不随机）
    default_session_key = f"agent:main:{user_id}"

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except RuntimeError as e:
                # 某些断连时机下，Starlette 可能抛出 RuntimeError（而非 WebSocketDisconnect）
                # 这里按正常断连处理，避免刷 ERROR 误导排障。
                text = str(e)
                if "not connected" in text.lower() or "accept first" in text.lower():
                    logger.info("[ws_stream] runtime disconnect user_id=%s device_id=%s err=%s", user_id, device_id, text)
                    break
                raise
            try:
                msg = json.loads(raw)
            except Exception:
                continue

            action = msg.get("action")
            msg_type = msg.get("type")
            method = msg.get("method")
            req_id = str(msg.get("id") or "")
            req_params = msg.get("params") if isinstance(msg.get("params"), dict) else {}

            logger.info(
                "[ws_stream] recv user_id=%s device_id=%s action=%s type=%s method=%s id=%s",
                user_id, device_id, action or "-", msg_type or "-", method or "-", req_id or "-",
            )

            is_chat_action = action == "chat"
            is_chat_req = (msg_type == "req" and method == "chat.send")

            if is_chat_action or is_chat_req:
                message = req_params.get("message", "") if is_chat_req else msg.get("message", "")
                # 优先使用客户端传入的 sessionKey，否则用稳定默认值
                session_key = (req_params.get("sessionKey") if is_chat_req else msg.get("sessionKey")) or default_session_key
                attachments = req_params.get("attachments") if is_chat_req else msg.get("attachments")
                model = req_params.get("model") if is_chat_req else msg.get("model")
                idempotency_key = (
                    req_params.get("idempotencyKey") if is_chat_req else msg.get("idempotencyKey")
                ) or uuid.uuid4().hex
                _bind_client_session(device_id, websocket, session_key)
                _mark_client_pending(device_id, websocket)

                if not manager.is_connected(device_id):
                    err_obj = {"type": "error", "error": "Device not connected"}
                    if is_chat_req and req_id:
                        err_obj = {"type": "res", "id": req_id, "ok": False, "error": "Device not connected"}
                    await websocket.send_text(json.dumps(err_obj, ensure_ascii=False))
                    continue

                if not message and not attachments:
                    err_obj = {"type": "error", "error": "message and attachments cannot both be empty"}
                    if is_chat_req and req_id:
                        err_obj = {
                            "type": "res",
                            "id": req_id,
                            "ok": False,
                            "error": "message and attachments cannot both be empty",
                        }
                    await websocket.send_text(json.dumps(err_obj, ensure_ascii=False))
                    continue

                try:
                    # 优先使用对话 RPC：chat.send
                    params = {
                        "sessionKey": session_key,
                        "message": message,
                        "idempotencyKey": idempotency_key,
                        "stream": True,
                    }
                    if attachments:
                        params["attachments"] = attachments
                    if model:
                        params["model"] = model
                    resp = await manager.send_request(
                        device_id,
                        "chat.send",
                        params,
                        timeout=120.0,
                    )
                    rpc_request_id = (
                        str(resp.get("request_id") or "").strip()
                        if isinstance(resp, dict) else ""
                    )
                    resp_data = resp.get("data") if isinstance(resp, dict) else resp
                    done_flag = bool(resp_data.get("done")) if isinstance(resp_data, dict) else False
                    run_id_from_resp = (
                        str(resp_data.get("runId") or resp_data.get("run_id") or "").strip()
                        if isinstance(resp_data, dict) else ""
                    )
                    if run_id_from_resp:
                        _bind_run_clients(device_id, run_id_from_resp, {websocket}, session_key=session_key)
                    if run_id_from_resp and idempotency_key:
                        await websocket.send_text(json.dumps({
                            "type": "chat_accepted",
                            "idempotencyKey": idempotency_key,
                            "runId": run_id_from_resp,
                        }, ensure_ascii=False))
                    if isinstance(resp_data, dict):
                        logger.info(
                            "[ws_stream] chat.send response user_id=%s device_id=%s keys=%s done=%s",
                            user_id, device_id, list(resp_data.keys()), done_flag,
                        )
                    else:
                        logger.info(
                            "[ws_stream] chat.send response user_id=%s device_id=%s type=%s",
                            user_id, device_id, type(resp_data).__name__,
                        )

                    logger.info(
                        "[ws_stream] dispatched chat.send user_id=%s device_id=%s session=%s rpc_request_id=%s",
                        user_id, device_id, session_key, rpc_request_id or "-",
                    )

                    # 兜底：若设备直接同步返回结果而没有后续 stream 事件，直接回 stream_end 给客户端
                    final_text = _extract_chat_text(resp_data)
                    if final_text or done_flag or not run_id_from_resp:
                        request_id = (
                            (rpc_request_id or None)
                            or (resp_data.get("runId") if isinstance(resp_data, dict) else None)
                            or (resp_data.get("run_id") if isinstance(resp_data, dict) else None)
                            or uuid.uuid4().hex
                        )
                        stream_end_payload = {
                            "type": "stream_end",
                            "request_id": request_id,
                            "data": {
                                "content": final_text or "",
                                "toolCalls": (
                                    resp_data.get("tool_calls")
                                    if isinstance(resp_data, dict) and isinstance(resp_data.get("tool_calls"), list)
                                    else []
                                ),
                            },
                        }
                        await websocket.send_text(json.dumps(stream_end_payload, ensure_ascii=False))

                    if is_chat_req and req_id:
                        await websocket.send_text(json.dumps({
                            "type": "res",
                            "id": req_id,
                            "ok": True,
                            "payload": {"accepted": True},
                        }, ensure_ascii=False))
                except Exception as e:
                    status_code = getattr(e, "status_code", None)
                    detail = getattr(e, "detail", str(e))
                    # chat.send 超时时不要再 fallback，避免重复调用和更长阻塞
                    if status_code == 504:
                        logger.warning("[ws_stream] chat.send timeout user_id=%s device_id=%s detail=%s", user_id, device_id, detail)
                        err_text = f"chat.send timeout: {detail}"
                        if is_chat_req and req_id:
                            await websocket.send_text(json.dumps({
                                "type": "res",
                                "id": req_id,
                                "ok": False,
                                "error": err_text,
                            }, ensure_ascii=False))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "error": err_text,
                            }, ensure_ascii=False))
                        continue

                    # 兼容旧设备：仅在非超时时降级到 HTTP 风格 chat/completions
                    logger.warning("[ws_stream] chat.send failed, fallback to v1/chat/completions: %s", e)
                    try:
                        fallback = {
                            "messages": [{"role": "user", "content": message or " "}],
                            "sessionKey": session_key,
                            "_stream": True,
                        }
                        if attachments:
                            fallback["attachments"] = attachments
                        if model:
                            fallback["model"] = model
                        await manager.send_request(
                            device_id,
                            "v1/chat/completions",
                            fallback,
                            method="POST",
                            timeout=180.0,
                        )
                        if is_chat_req and req_id:
                            await websocket.send_text(json.dumps({
                                "type": "res",
                                "id": req_id,
                                "ok": True,
                                "payload": {"accepted": True, "fallback": True},
                            }, ensure_ascii=False))
                    except Exception as e2:
                        if is_chat_req and req_id:
                            await websocket.send_text(json.dumps({
                                "type": "res",
                                "id": req_id,
                                "ok": False,
                                "error": str(e2),
                            }, ensure_ascii=False))
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "error": str(e2),
                            }, ensure_ascii=False))
            elif action == "ping" or (msg_type == "req" and method == "ping"):
                if msg_type == "req" and req_id:
                    await websocket.send_text(json.dumps({
                        "type": "res",
                        "id": req_id,
                        "ok": True,
                        "payload": {"pong": True},
                    }, ensure_ascii=False))
                else:
                    await websocket.send_text(json.dumps({"type": "pong"}, ensure_ascii=False))
            elif msg_type == "req" and req_id:
                await websocket.send_text(json.dumps({
                    "type": "res",
                    "id": req_id,
                    "ok": False,
                    "error": f"unsupported method: {method or action or ''}",
                }, ensure_ascii=False))

    except WebSocketDisconnect:
        logger.info("[ws_stream] disconnect user_id=%s device_id=%s", user_id, device_id)
    except Exception:
        logger.exception("[ws_stream] error user_id=%s device_id=%s", user_id, device_id)
    finally:
        _unregister_stream_client(device_id, websocket)

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
    uvicorn.run(app, host="0.0.0.0", port=PORT, ws_max_size=2 * 1024 * 1024)
