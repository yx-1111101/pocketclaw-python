"""OpenClaw Gateway WebSocket 客户端（含流式 chat）"""
import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Callable, Any

import websockets

logger = logging.getLogger("uvicorn.error")

GATEWAY_WS_URL = "ws://127.0.0.1:18789"
GATEWAY_TOKEN = "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c"
GATEWAY_ORIGIN = "http://localhost:18789"
REQUEST_TIMEOUT = 15.0
STREAM_TIMEOUT = 120.0

CONNECT_PARAMS = {
    "minProtocol": 3,
    "maxProtocol": 3,
    "role": "operator",
    "scopes": ["operator.read", "operator.write", "operator.admin"],
    "auth": {"token": GATEWAY_TOKEN},
    "client": {
        "id": "webchat-ui",
        "version": "1.0.0",
        "platform": "linux",
        "mode": "webchat",
    },
    "caps": [],
    "commands": [],
    "permissions": {},
}


async def _connect_gateway(ws):
    """完成 Gateway WS 握手，返回 hello payload"""
    await asyncio.wait_for(ws.recv(), timeout=5)  # challenge
    conn_id = str(uuid.uuid4())
    await ws.send(json.dumps({"type": "req", "id": conn_id, "method": "connect", "params": CONNECT_PARAMS}))
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    hello = json.loads(raw)
    if not hello.get("ok"):
        raise RuntimeError(f"Gateway connect failed: {hello.get('error', {}).get('message')}")
    return hello.get("payload", {})


async def gateway_request(method: str, params: dict = None) -> dict:
    """单次请求-响应"""
    try:
        async with websockets.connect(
            GATEWAY_WS_URL,
            additional_headers={"Origin": GATEWAY_ORIGIN},
            open_timeout=5,
        ) as ws:
            await _connect_gateway(ws)
            req_id = str(uuid.uuid4())
            await ws.send(json.dumps({"type": "req", "id": req_id, "method": method, "params": params or {}}))

            deadline = asyncio.get_event_loop().time() + REQUEST_TIMEOUT
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError()
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                data = json.loads(raw)
                if data.get("type") == "res" and data.get("id") == req_id:
                    if not data.get("ok"):
                        raise RuntimeError(f"Gateway error: {data.get('error', {}).get('message')}")
                    return data.get("payload", {})
    except Exception as e:
        logger.error("[gateway_client] %s %s: %s", method, params, e)
        raise


async def gateway_chat_stream(
    message: str,
    model: str,
    session_key: str = "main",
    on_delta: Callable[[str], Any] = None,
    on_final: Callable[[str, str], Any] = None,
    on_error: Callable[[str], Any] = None,
) -> str:
    """
    流式 chat.send，返回 runId（可用于 abort）
    on_delta(text): 每个 delta chunk 回调
    on_final(run_id, full_text): 完成时回调
    on_error(message): 出错时回调
    """
    run_id = None
    try:
        async with websockets.connect(
            GATEWAY_WS_URL,
            additional_headers={"Origin": GATEWAY_ORIGIN},
            open_timeout=5,
        ) as ws:
            await _connect_gateway(ws)

            req_id = str(uuid.uuid4())
            idempotency_key = str(uuid.uuid4())
            await ws.send(json.dumps({
                "type": "req",
                "id": req_id,
                "method": "chat.send",
                "params": {
                    "message": message,
                    "sessionKey": session_key,
                    "idempotencyKey": idempotency_key,
                    "deliver": False,
                },
            }))

            # 等 ack（拿 runId）
            deadline = asyncio.get_event_loop().time() + 10
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError("ack timeout")
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                data = json.loads(raw)
                if data.get("type") == "res" and data.get("id") == req_id:
                    if not data.get("ok"):
                        raise RuntimeError(data.get("error", {}).get("message", "chat.send failed"))
                    run_id = data.get("payload", {}).get("runId")
                    break

            # 接收流式事件
            full_text = ""
            deadline = asyncio.get_event_loop().time() + STREAM_TIMEOUT
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0:
                    raise asyncio.TimeoutError("stream timeout")
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                data = json.loads(raw)

                if data.get("type") != "event":
                    continue
                payload = data.get("payload", {})
                state = payload.get("state")

                if state == "delta":
                    delta = payload.get("delta", "")
                    full_text += delta
                    if on_delta and delta:
                        await on_delta(delta)

                elif state == "final":
                    full_content = payload.get("content") or full_text
                    if on_final:
                        await on_final(run_id, full_content)
                    break

                elif state == "error":
                    err_msg = payload.get("message", "stream error")
                    if on_error:
                        await on_error(err_msg)
                    break

    except Exception as e:
        logger.error("[gateway_chat_stream] error: %s", e)
        if on_error:
            try:
                await on_error(str(e))
            except Exception:
                pass

    return run_id


async def gateway_chat_abort(run_id: str, session_key: str = "main"):
    """中止正在运行的 chat"""
    try:
        await gateway_request("chat.abort", {"runId": run_id, "sessionKey": session_key})
    except Exception as e:
        logger.warning("[gateway_chat_abort] %s: %s", run_id, e)


async def gateway_chat_history(session_key: str = "main", limit: int = 50) -> list:
    """获取 chat 历史"""
    try:
        payload = await gateway_request("chat.history", {"sessionKey": session_key, "limit": limit})
        return payload.get("messages", [])
    except Exception as e:
        logger.error("[gateway_chat_history] %s", e)
        return []
