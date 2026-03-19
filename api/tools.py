"""
Tools/ACP 管理 API - 调用真实 Gateway RPC
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import logging

from app.core.gateway_rpc import call_gateway_rpc_sync

router = APIRouter(prefix="/tools", tags=["tools"])
logger = logging.getLogger(__name__)


@router.get("")
async def list_tools():
    """获取可用工具列表 - 从 Gateway acp.list 获取"""
    try:
        result = call_gateway_rpc_sync("acp.list", timeout=15.0)
        
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
    tool: str = None,
    args: str = None
):
    """调用工具 - 通过 Gateway acp.invoke"""
    if not tool:
        return {"success": False, "error": "tool parameter is required"}
    
    try:
        import json
        params = {"tool": tool}
        if args:
            try:
                params["args"] = json.loads(args)
            except:
                params["args"] = {"raw": args}
        
        result = call_gateway_rpc_sync("acp.invoke", params, timeout=30.0)
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


# ========== ACP 别名路由 ==========

acp_router = APIRouter(prefix="/acp", tags=["acp"])


@acp_router.get("/tools")
async def list_acp_tools():
    """获取 ACP 工具列表 (acp.list 别名)"""
    return await list_tools()


@acp_router.get("/tools/invoke")
async def invoke_acp_tool(
    tool: str = None,
    args: str = None
):
    """调用 ACP 工具"""
    return await invoke_tool(tool=tool, args=args)
