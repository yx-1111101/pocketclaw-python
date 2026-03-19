"""
用量统计 API - 调用设备端 Gateway
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.supabase import get_db

router = APIRouter(prefix="/usage", tags=["用量统计"])
logger = logging.getLogger(__name__)


@router.get("/sessions/{session_key}")
async def session_usage(
    device_id: str = None,
    session_key: str = None,
    request: Request = None
):
    """获取指定会话的用量统计"""
    if not device_id or not session_key or not request:
        return {"success": False, "error": "device_id and session_key required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        result = await manager.send_request(
            device_id, 
            "sessions.usage", 
            {"sessionKey": session_key},
            timeout=10.0
        )
        
        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result.get("error")}
        
        return {"success": True, "usage": result}
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/summary")
async def usage_summary(
    device_id: str = None,
    request: Request = None
):
    """获取用量汇总 - 所有会话的用量统计"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 获取会话列表
        sessions_result = await manager.send_request(
            device_id,
            "sessions.list",
            {},
            timeout=10.0
        )
        
        sessions = sessions_result.get("sessions", []) if isinstance(sessions_result, dict) else []
        
        # 汇总所有用量
        total_tokens = 0
        total_requests = 0
        session_usages = []
        
        for session in sessions[:10]:  # 取前10个会话
            session_key = session.get("key")
            if session_key:
                try:
                    usage_result = await manager.send_request(
                        device_id,
                        "sessions.usage",
                        {"sessionKey": session_key},
                        timeout=5.0
                    )
                    usage = usage_result if isinstance(usage_result, dict) else {}
                    session_usages.append({
                        "sessionKey": session_key,
                        "label": session.get("label", session_key),
                        "usage": usage
                    })
                    total_tokens += usage.get("total_tokens", 0)
                    total_requests += usage.get("total_requests", 0)
                except:
                    pass
        
        return {
            "success": True,
            "summary": {
                "totalTokens": total_tokens,
                "totalRequests": total_requests,
                "sessionsCount": len(sessions),
                "sessions": session_usages
            }
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/models")
async def model_usage(
    device_id: str = None,
    request: Request = None
):
    """获取各模型的用量统计"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 获取模型列表
        models_result = await manager.send_request(
            device_id,
            "models.list",
            {},
            timeout=10.0
        )
        
        models = models_result.get("models", []) if isinstance(models_result, dict) else []
        
        # 简化返回 - 实际用量需要从会话统计中汇总
        return {
            "success": True,
            "models": [
                {
                    "id": m.get("key"),
                    "name": m.get("name"),
                    "available": m.get("available", True),
                    "tags": m.get("tags", [])
                }
                for m in models
            ]
        }
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/quota")
async def quota_info(
    device_id: str = None,
    request: Request = None
):
    """获取配额信息"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    # TODO: 从计费系统获取真实配额
    # 当前返回模拟数据
    return {
        "success": True,
        "quota": {
            "type": "free",  # free / pro / enterprise
            "limit": {
                "sessions": 100,
                "storage": 1024,  # MB
                "apiCalls": 10000
            },
            "used": {
                "sessions": 3,
                "storage": 50,
                "apiCalls": 1500
            }
        }
    }
