"""OpenClaw Gateway WebSocket 客户端"""
import asyncio
import json
import logging
import uuid
from typing import Any, Optional

import websockets

logger = logging.getLogger("uvicorn.error")

GATEWAY_WS_URL = "ws://127.0.0.1:18789"
GATEWAY_TOKEN = "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c"
GATEWAY_ORIGIN = "http://localhost:18789"
REQUEST_TIMEOUT = 15.0


async def gateway_request(method: str, params: dict = None) -> dict:
    """向本地 Gateway 发一次 WS 请求，返回 payload"""
    try:
        async with websockets.connect(
            GATEWAY_WS_URL,
            additional_headers={"Origin": GATEWAY_ORIGIN},
            open_timeout=5,
        ) as ws:
            # 1. 收 challenge
            await asyncio.wait_for(ws.recv(), timeout=5)

            # 2. connect
            conn_id = str(uuid.uuid4())
            await ws.send(json.dumps({
                "type": "req",
                "id": conn_id,
                "method": "connect",
                "params": {
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
                },
            }))

            raw = await asyncio.wait_for(ws.recv(), timeout=5)
            hello = json.loads(raw)
            if not hello.get("ok"):
                raise RuntimeError(f"Gateway connect failed: {hello.get('error', {}).get('message')}")

            # 3. 发请求
            req_id = str(uuid.uuid4())
            await ws.send(json.dumps({
                "type": "req",
                "id": req_id,
                "method": method,
                "params": params or {},
            }))

            # 4. 等响应（跳过 event 帧）
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
