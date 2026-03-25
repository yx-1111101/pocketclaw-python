"""
Token 用量与费用 API - 详细的用量分析和费用计算
"""
from fastapi import APIRouter, HTTPException, Request
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging

from app.core.websocket import manager
from api.proxy import _require_user_device
from app.core.db import get_db

router = APIRouter(prefix="/billing", tags=["用量与费用"])
logger = logging.getLogger(__name__)


# 模型定价 (单位: $ / 1M tokens)
MODEL_PRICING = {
    # OpenAI
    "gpt-4o": {"input": 2.5, "output": 10.0, "name": "GPT-4o"},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6, "name": "GPT-4o Mini"},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0, "name": "GPT-4 Turbo"},
    "gpt-4": {"input": 30.0, "output": 60.0, "name": "GPT-4"},
    "gpt-3.5-turbo": {"input": 0.5, "output": 1.5, "name": "GPT-3.5 Turbo"},
    
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "name": "Claude Sonnet 4"},
    "claude-opus-4-5": {"input": 15.0, "output": 75.0, "name": "Claude Opus 4"},
    "claude-3-5-sonnet": {"input": 3.0, "output": 15.0, "name": "Claude 3.5 Sonnet"},
    "claude-3-opus": {"input": 15.0, "output": 75.0, "name": "Claude 3 Opus"},
    "claude-3-sonnet": {"input": 3.0, "output": 15.0, "name": "Claude 3 Sonnet"},
    "claude-3-haiku": {"input": 0.25, "output": 1.25, "name": "Claude 3 Haiku"},
    
    # MiniMax
    "MiniMax-M2.5": {"input": 0.0, "output": 0.0, "name": "MiniMax M2.5"},
    "minimax/MiniMax-M2.5": {"input": 0.0, "output": 0.0, "name": "MiniMax M2.5"},
    "minimax-portal/MiniMax-M2.5": {"input": 0.0, "output": 0.0, "name": "MiniMax M2.5"},
    
    # DeepSeek
    "deepseek-chat": {"input": 0.14, "output": 0.28, "name": "DeepSeek Chat"},
    "deepseek-coder": {"input": 0.14, "output": 0.28, "name": "DeepSeek Coder"},
    
    # Google
    "gemini-1.5-pro": {"input": 1.25, "output": 5.0, "name": "Gemini 1.5 Pro"},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.3, "name": "Gemini 1.5 Flash"},
    
    # Moonshot
    "moonshot-v1-8k": {"input": 0.6, "output": 0.9, "name": "Moonshot V1 8K"},
    "moonshot-v1-32k": {"input": 0.9, "output": 1.3, "name": "Moonshot V1 32K"},
    
    # Qwen
    "qwen-turbo": {"input": 0.2, "output": 0.6, "name": "Qwen Turbo"},
    "qwen-plus": {"input": 0.4, "output": 1.2, "name": "Qwen Plus"},
    "qwen-max": {"input": 2.0, "output": 6.0, "name": "Qwen Max"},
    
    # 默认
    "default": {"input": 1.0, "output": 3.0, "name": "默认模型"}
}


def _get_model_price(model_key: str) -> Dict:
    """获取模型定价"""
    # 精确匹配
    if model_key in MODEL_PRICING:
        return MODEL_PRICING[model_key]
    
    # 模糊匹配
    model_lower = model_key.lower()
    for key, price in MODEL_PRICING.items():
        if key in model_lower or model_lower in key:
            return price
    
    return MODEL_PRICING["default"]


def _calculate_cost(tokens: int, model_key: str, is_output: bool = False) -> float:
    """计算费用"""
    price = _get_model_price(model_key)
    rate = price["output"] if is_output else price["input"]
    return (tokens / 1_000_000) * rate


@router.get("/overview")
async def billing_overview(
    device_id: str = None,
    request: Request = None,
    days: int = 30
):
    """获取费用概览 - 总览数据"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 获取会话列表
        sessions_result = await manager.send_request(
            device_id, "sessions.list", {}, timeout=10.0
        )
        sessions = sessions_result.get("sessions", []) if isinstance(sessions_result, dict) else []
        
        # 统计所有用量
        total_input_tokens = 0
        total_output_tokens = 0
        model_usage = {}
        
        for session in sessions:
            session_key = session.get("key")
            if session_key:
                try:
                    usage_result = await manager.send_request(
                        device_id, "sessions.usage", {"sessionKey": session_key}, timeout=5.0
                    )
                    usage = usage_result if isinstance(usage_result, dict) else {}
                    
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    model = usage.get("model", "default")
                    
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    
                    if model not in model_usage:
                        model_usage[model] = {"input": 0, "output": 0, "requests": 0}
                    model_usage[model]["input"] += input_tokens
                    model_usage[model]["output"] += output_tokens
                    model_usage[model]["requests"] += 1
                    
                except:
                    pass
        
        total_tokens = total_input_tokens + total_output_tokens
        
        # 计算费用
        total_cost = 0.0
        model_costs = []
        for model, usage in model_usage.items():
            price = _get_model_price(model)
            input_cost = _calculate_cost(usage["input"], model, False)
            output_cost = _calculate_cost(usage["output"], model, True)
            cost = input_cost + output_cost
            total_cost += cost
            
            model_costs.append({
                "model": model,
                "name": price["name"],
                "inputTokens": usage["input"],
                "outputTokens": usage["output"],
                "totalTokens": usage["input"] + usage["output"],
                "requests": usage["requests"],
                "cost": round(cost, 4),
                "inputCost": round(input_cost, 4),
                "outputCost": round(output_cost, 4)
            })
        
        # 按费用排序
        model_costs.sort(key=lambda x: x["cost"], reverse=True)
        
        return {
            "success": True,
            "overview": {
                "periodDays": days,
                "totalTokens": total_tokens,
                "totalInputTokens": total_input_tokens,
                "totalOutputTokens": total_output_tokens,
                "totalCost": round(total_cost, 4),
                "currency": "USD",
                "modelsCount": len(model_usage),
                "sessionsCount": len(sessions)
            },
            "byModel": model_costs[:10]  # Top 10
        }
        
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/daily")
async def billing_daily(
    device_id: str = None,
    request: Request = None,
    days: int = 30
):
    """获取每日用量趋势"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 获取会话列表
        sessions_result = await manager.send_request(
            device_id, "sessions.list", {}, timeout=10.0
        )
        sessions = sessions_result.get("sessions", []) if isinstance(sessions_result, dict) else []
        
        # 按天统计
        daily_data = {}
        
        for session in sessions:
            session_key = session.get("key")
            if session_key:
                try:
                    usage_result = await manager.send_request(
                        device_id, "sessions.usage", {"sessionKey": session_key}, timeout=5.0
                    )
                    usage = usage_result if isinstance(usage_result, dict) else {}
                    
                    # 尝试获取时间戳
                    created_at = usage.get("created_at") or usage.get("createdAt")
                    if created_at:
                        date = created_at[:10] if isinstance(created_at, str) else "unknown"
                    else:
                        date = "recent"
                    
                    if date not in daily_data:
                        daily_data[date] = {"tokens": 0, "cost": 0.0, "requests": 0}
                    
                    input_tokens = usage.get("input_tokens", 0)
                    output_tokens = usage.get("output_tokens", 0)
                    model = usage.get("model", "default")
                    
                    daily_data[date]["tokens"] += input_tokens + output_tokens
                    daily_data[date]["cost"] += _calculate_cost(input_tokens, model) + _calculate_cost(output_tokens, model, True)
                    daily_data[date]["requests"] += 1
                    
                except:
                    pass
        
        # 转换为列表
        daily_list = [
            {
                "date": date,
                "tokens": data["tokens"],
                "cost": round(data["cost"], 4),
                "requests": data["requests"]
            }
            for date, data in sorted(daily_data.items(), reverse=True)
        ]
        
        return {
            "success": True,
            "daily": daily_list[:days]
        }
        
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/models")
async def billing_models(
    device_id: str = None,
    request: Request = None
):
    """获取各模型的用量和费用详情"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        db = get_db()
        await _require_user_device(db, request, device_id)
        
        # 获取模型列表
        models_result = await manager.send_request(
            device_id, "models.list", {}, timeout=10.0
        )
        models = models_result.get("models", []) if isinstance(models_result, dict) else []
        
        # 获取用量统计
        overview_result = await billing_overview(device_id, request, 30)
        
        model_list = []
        for m in models:
            model_key = m.get("key", "")
            price = _get_model_price(model_key)
            
            # 查找该模型的用量
            usage = next((u for u in overview_result.get("byModel", []) if u["model"] == model_key), None)
            
            model_list.append({
                "id": model_key,
                "name": m.get("name", model_key),
                "available": m.get("available", True),
                "pricing": {
                    "input": price["input"],
                    "output": price["output"],
                    "unit": "$/M tokens"
                },
                "usage": usage or {
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "totalTokens": 0,
                    "cost": 0
                }
            })
        
        return {
            "success": True,
            "models": model_list
        }
        
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}


@router.get("/chart")
async def billing_chart(
    device_id: str = None,
    request: Request = None,
    days: int = 30
):
    """获取图表数据 - 用于前端展示"""
    if not device_id or not request:
        return {"success": False, "error": "device_id required"}
    
    try:
        # 获取概览
        overview = await billing_overview(device_id, request, days)
        
        # 获取每日数据
        daily = await billing_daily(device_id, request, days)
        
        # 获取模型分布
        overview_data = overview.get("overview", {})
        by_model = overview.get("byModel", [])
        
        # 饼图数据
        pie_chart = [
            {
                "name": m["name"],
                "value": m["totalTokens"],
                "cost": m["cost"]
            }
            for m in by_model[:6]
        ]
        
        # 折线图数据
        line_chart = daily.get("daily", [])
        
        return {
            "success": True,
            "chart": {
                "pie": pie_chart,
                "line": line_chart,
                "summary": {
                    "totalTokens": overview_data.get("totalTokens", 0),
                    "totalCost": overview_data.get("totalCost", 0),
                    "modelsCount": overview_data.get("modelsCount", 0),
                    "currency": "USD"
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Exception: {e}")
        return {"success": False, "error": str(e)}
