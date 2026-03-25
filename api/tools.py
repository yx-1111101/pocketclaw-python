"""
Tools/ACP 管理 API - 调用设备端 Gateway RPC
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging
import json

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.db import get_db

router = APIRouter(prefix="/tools", tags=["tools"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_tools(device_id: str = None, request: Request = None):
    """获取可用工具列表 - 从设备端 Gateway acp.list 获取"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required", "tools": [], "count": 0}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        result = await manager.send_request(device_id, "acp.list", {}, method="GET", timeout=15.0)
        
        if isinstance(result, dict) and "error" in result:
            logger.error(f"Failed to get tools: {result}")
            return {"success": False, "error": result.get("error"), "tools": [], "count": 0}
        
        tools = result.get("tools", []) if isinstance(result, dict) else []
        
        return {
            "success": True,
            "tools": tools,
            "count": len(tools)
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e), "tools": [], "count": 0}


@router.get("/invoke")
async def invoke_tool(
    device_id: str = None,
    request: Request = None,
    tool: str = None,
    args: str = None
):
    """调用工具 - 通过设备端 Gateway acp.invoke"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    if not tool:
        return {"success": False, "error": "tool parameter is required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        params = {"tool": tool}
        if args:
            try:
                params["args"] = json.loads(args)
            except:
                params["args"] = {"raw": args}
        
        result = await manager.send_request(device_id, "acp.invoke", params, timeout=30.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


# ========== ACP 别名路由 ==========

acp_router = APIRouter(prefix="/acp", tags=["acp"])


@acp_router.get("/tools")
async def list_acp_tools(device_id: str = None, request: Request = None):
    """获取 ACP 工具列表 (acp.list 别名)"""
    return await list_tools(device_id=device_id, request=request)


@acp_router.get("/tools/invoke")
async def invoke_acp_tool(
    device_id: str = None,
    request: Request = None,
    tool: str = None,
    args: str = None
):
    """调用 ACP 工具"""
    return await invoke_tool(device_id=device_id, request=request, tool=tool, args=args)
