"""WebSocket 连接管理"""
import logging
import os
import json
import uuid
import asyncio
from typing import Dict, Optional
from fastapi import WebSocket

logger = logging.getLogger("uvicorn.error")
GATEWAY_TOKEN = os.getenv("GATEWAY_TOKEN", "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c")

# 普通 API 调用超时（状态查询、文件等）
DEFAULT_TIMEOUT = 30.0
# LLM 推理超时（模型冷启动 + 生成时间）
CHAT_TIMEOUT = 180.0

CHAT_PATHS = frozenset({
    "v1/chat/completions",
    "chat/completions",
})


class ConnectionManager:
    """管理设备 WebSocket 连接（设备侧）"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
        # 每个设备对应的小程序客户端 WS（用于流式推送）
        self.client_connections: Dict[str, WebSocket] = {}

    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
        logger.info("[ws_manager] connected device_id=%s active=%s", device_id, len(self.active_connections))

    def disconnect(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]
        logger.info("[ws_manager] disconnected device_id=%s active=%s", device_id, len(self.active_connections))

    def is_connected(self, device_id: str) -> bool:
        return device_id in self.active_connections

    # ── 小程序客户端连接管理 ──────────────────────────────

    def connect_client(self, device_id: str, websocket: WebSocket):
        self.client_connections[device_id] = websocket
        logger.info("[ws_manager] client connected device_id=%s", device_id)

    def disconnect_client(self, device_id: str):
        self.client_connections.pop(device_id, None)
        logger.info("[ws_manager] client disconnected device_id=%s", device_id)

    async def push_to_client(self, device_id: str, data: dict):
        """将消息推送给小程序客户端"""
        ws = self.client_connections.get(device_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception as e:
                logger.warning("[ws_manager] push_to_client failed device_id=%s err=%s", device_id, e)

    # ── 向设备发送请求（请求-响应模式）────────────────────

    async def send_request(
        self,
        device_id: str,
        function: str,
        params: dict = None,
        method: str = "POST",
        query: dict = None,
        headers: dict = None,
        timeout: float = None,
    ) -> dict:
        if device_id not in self.active_connections:
            from fastapi import HTTPException
            logger.warning("[ws_manager] device not connected device_id=%s function=%s", device_id, function)
            raise HTTPException(status_code=404, detail=f"Device {device_id} not connected")

        websocket = self.active_connections[device_id]
        request_id = str(uuid.uuid4())

        payload_params = dict(params or {})
        payload_params["_method"] = method
        if query:
            payload_params["_query"] = query
        if headers:
            payload_params["_headers"] = headers

        payload = {
            "request_id": request_id,
            "function": function,
            "params": payload_params,
            "gateway_token": GATEWAY_TOKEN,
        }

        if timeout is None:
            timeout = CHAT_TIMEOUT if function in CHAT_PATHS else DEFAULT_TIMEOUT

        logger.info(
            "[ws_manager] send request_id=%s device_id=%s function=%s timeout=%ss",
            request_id, device_id, function, timeout,
        )

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_requests[request_id] = future

        try:
            await websocket.send_text(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.info("[ws_manager] recv request_id=%s device_id=%s", request_id, device_id)
            return {"status": "success", "data": result}
        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            from fastapi import HTTPException
            raise HTTPException(status_code=504, detail="Request timeout")
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(e))

    async def handle_response(self, request_id: str, data: dict):
        """处理设备返回的响应"""
        if request_id in self.pending_requests:
            self.pending_requests[request_id].set_result(data)
            del self.pending_requests[request_id]
            logger.info("[ws_manager] resolved request_id=%s", request_id)
        else:
            logger.warning("[ws_manager] orphan response request_id=%s", request_id)

    # ── 流式消息处理（设备推送过来的 chunk）──────────────

    async def handle_stream_chunk(self, device_id: str, data: dict):
        """收到设备的流式 chunk，转发给小程序"""
        await self.push_to_client(device_id, {
            "type": "stream",
            **data
        })


manager = ConnectionManager()
