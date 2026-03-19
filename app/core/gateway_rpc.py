"""
Gateway RPC 调用辅助模块

用于从 PocketClaw Cloud 调用本地 Gateway 的 WebSocket RPC 接口
"""
import asyncio
import json
import uuid
import websockets
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Gateway 配置
GATEWAY_WS_URL = "ws://127.0.0.1:18789"
GATEWAY_TOKEN = "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c"


async def call_gateway_rpc(function: str, params: Optional[Dict] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """
    调用 Gateway WebSocket RPC
    
    Args:
        function: RPC 方法名 (如 "skills.list", "models.list")
        params: 参数字典
        timeout: 超时时间(秒)
    
    Returns:
        RPC 响应结果
    """
    if params is None:
        params = {}
    
    request_id = str(uuid.uuid4())
    
    payload = {
        "id": request_id,
        "function": function,
        "params": params
    }
    
    try:
        async with websockets.connect(f"{GATEWAY_WS_URL}?token={GATEWAY_TOKEN}") as ws:
            await ws.send(json.dumps(payload))
            
            # 等待响应
            response = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(response)
            
            # 返回结果
            if "result" in data:
                return data["result"]
            elif "error" in data:
                logger.error(f"[gateway_rpc] error: {data['error']}")
                return {"error": data["error"]}
            else:
                return data
                
    except asyncio.TimeoutError:
        logger.error(f"[gateway_rpc] timeout: {function}")
        return {"error": "Gateway timeout"}
    except Exception as e:
        logger.error(f"[gateway_rpc] exception: {e}")
        return {"error": str(e)}


def call_gateway_rpc_sync(function: str, params: Optional[Dict] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """
    同步版本的 Gateway RPC 调用
    """
    return asyncio.run(call_gateway_rpc(function, params, timeout))
