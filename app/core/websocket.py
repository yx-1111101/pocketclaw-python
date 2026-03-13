"""WebSocket 连接管理"""
import json
import uuid
import asyncio
from typing import Dict
from fastapi import WebSocket


DEFAULT_TIMEOUT = 30.0
CHAT_TIMEOUT = 180.0

CHAT_PATHS = frozenset({
    "v1/chat/completions",
    "chat/completions",
})


class ConnectionManager:
    """管理设备 WebSocket 连接"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pending_requests: Dict[str, asyncio.Future] = {}
    
    async def connect(self, device_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_id] = websocket
    
    def disconnect(self, device_id: str):
        if device_id in self.active_connections:
            del self.active_connections[device_id]

    def is_connected(self, device_id: str) -> bool:
        return device_id in self.active_connections

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
        }

        if timeout is None:
            timeout = CHAT_TIMEOUT if function in CHAT_PATHS else DEFAULT_TIMEOUT

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending_requests[request_id] = future
        
        try:
            await websocket.send_text(json.dumps(payload))
            result = await asyncio.wait_for(future, timeout=timeout)
            return {"status": "success", "data": result}
        except asyncio.TimeoutError:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            from fastapi import HTTPException
            raise HTTPException(status_code=504, detail="Request timeout")
        except Exception as e:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]
            from fastapi import HTTPException
            raise HTTPException(status_code=500, detail=str(e))
    
    async def handle_response(self, request_id: str, data: dict):
        if request_id in self.pending_requests:
            self.pending_requests[request_id].set_result(data)
            del self.pending_requests[request_id]


manager = ConnectionManager()
