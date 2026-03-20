"""Cron 任务管理 API（顶层 /cron，底层调用设备 Gateway cron.* RPC）"""
from fastapi import APIRouter, Request
from typing import Any, Dict, Optional
import logging

from app.core.websocket import manager
from app.core.supabase import get_db
from api.proxy import _require_user_device

router = APIRouter(prefix="/cron", tags=["定时任务"])
logger = logging.getLogger(__name__)


def _rpc_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else {}


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


async def _read_json_body(request: Request) -> Dict[str, Any]:
    if not request:
        return {}
    try:
        body = await request.json()
        return body if isinstance(body, dict) else {}
    except Exception:
        return {}


async def _resolve_device_id(device_id: Optional[str], request: Request, body: Dict[str, Any] = None) -> str:
    did = _norm_text(device_id)
    if did:
        return did
    if isinstance(body, dict):
        return _norm_text(body.get("device_id"))
    parsed = await _read_json_body(request)
    return _norm_text(parsed.get("device_id"))


@router.get("")
async def list_cron(device_id: str = None, request: Request = None):
    """获取所有 cron 任务"""
    if not request:
        return {"success": False, "error": "device_id required", "jobs": [], "count": 0}

    try:
        device_id = await _resolve_device_id(device_id, request)
        if not device_id:
            return {"success": False, "error": "device_id required", "jobs": [], "count": 0}

        db = get_db()
        await _require_user_device(db, request, device_id)

        if not manager.is_connected(device_id):
            return {
                "success": True,
                "jobs": [],
                "count": 0,
                "total": 0,
                "offline": True,
                "message": "设备离线",
            }

        result = await manager.send_request(device_id, "cron.list", {}, timeout=15.0)
        payload = _rpc_payload(result)
        if payload.get("error"):
            return {"success": False, "error": payload.get("error"), "jobs": [], "count": 0}

        jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
        return {
            "success": True,
            "jobs": jobs,
            "count": len(jobs),
            "total": int(payload.get("total") or len(jobs)),
            "offset": payload.get("offset"),
            "limit": payload.get("limit"),
            "hasMore": payload.get("hasMore"),
            "nextOffset": payload.get("nextOffset"),
            "offline": False,
        }
    except Exception as e:
        logger.error(f"[cron.list] {e}")
        return {"success": False, "error": str(e), "jobs": [], "count": 0}


@router.post("")
async def add_cron(device_id: str = None, request: Request = None):
    """创建 cron 任务"""
    if not request:
        return {"success": False, "error": "device_id required"}

    try:
        body = await _read_json_body(request)
        device_id = await _resolve_device_id(device_id, request, body)
        if not device_id:
            return {"success": False, "error": "device_id required"}

        db = get_db()
        await _require_user_device(db, request, device_id)

        schedule = body.get("schedule")
        if not isinstance(schedule, dict):
            return {"success": False, "error": "schedule required"}

        payload = body.get("payload")
        if not isinstance(payload, dict):
            msg = _norm_text(body.get("message"))
            if not msg:
                return {"success": False, "error": "payload or message required"}
            payload = {"kind": "agentTurn", "message": msg}

        name = _norm_text(body.get("name"))
        session_target = _norm_text(body.get("session_target") or body.get("sessionTarget") or "isolated")
        enabled = bool(body.get("enabled", True))
        delivery = body.get("delivery")

        job: Dict[str, Any] = {
            "schedule": schedule,
            "payload": payload,
            "sessionTarget": session_target or "isolated",
            "enabled": enabled,
        }
        if name:
            job["name"] = name
        if isinstance(delivery, dict):
            job["delivery"] = delivery

        result = await manager.send_request(device_id, "cron.add", {"job": job}, timeout=15.0)
        rpc = _rpc_payload(result)
        if rpc.get("error"):
            return {"success": False, "error": rpc.get("error")}
        return {"success": True, "job": rpc.get("job") if isinstance(rpc.get("job"), dict) else {}}
    except Exception as e:
        logger.error(f"[cron.add] {e}")
        return {"success": False, "error": str(e)}


@router.patch("/{job_id}")
async def update_cron(job_id: str, device_id: str = None, request: Request = None):
    """更新 cron 任务"""
    if not request:
        return {"success": False, "error": "device_id required"}

    try:
        body = await _read_json_body(request)
        device_id = await _resolve_device_id(device_id, request, body)
        if not device_id:
            return {"success": False, "error": "device_id required"}

        db = get_db()
        await _require_user_device(db, request, device_id)

        patch: Dict[str, Any] = {}
        for k in ("enabled", "name", "schedule", "payload"):
            if k in body and body.get(k) is not None:
                patch[k] = body.get(k)
        if not patch:
            return {"success": False, "error": "No fields to update"}

        result = await manager.send_request(
            device_id,
            "cron.update",
            {"jobId": job_id, "patch": patch},
            timeout=15.0,
        )
        rpc = _rpc_payload(result)
        if rpc.get("error"):
            return {"success": False, "error": rpc.get("error")}
        return {"success": True, "job": rpc.get("job") if isinstance(rpc.get("job"), dict) else {}}
    except Exception as e:
        logger.error(f"[cron.update] {e}")
        return {"success": False, "error": str(e)}


@router.delete("/{job_id}")
async def delete_cron(job_id: str, device_id: str = None, request: Request = None):
    """删除 cron 任务"""
    if not request:
        return {"success": False, "error": "device_id required"}

    try:
        device_id = await _resolve_device_id(device_id, request)
        if not device_id:
            return {"success": False, "error": "device_id required"}

        db = get_db()
        await _require_user_device(db, request, device_id)

        result = await manager.send_request(device_id, "cron.remove", {"jobId": job_id}, timeout=15.0)
        rpc = _rpc_payload(result)
        if rpc.get("error"):
            return {"success": False, "error": rpc.get("error")}
        return {"success": True}
    except Exception as e:
        logger.error(f"[cron.delete] {e}")
        return {"success": False, "error": str(e)}


@router.post("/{job_id}/run")
async def run_cron(job_id: str, device_id: str = None, request: Request = None):
    """立即执行 cron 任务"""
    if not request:
        return {"success": False, "error": "device_id required"}

    try:
        device_id = await _resolve_device_id(device_id, request)
        if not device_id:
            return {"success": False, "error": "device_id required"}

        db = get_db()
        await _require_user_device(db, request, device_id)

        result = await manager.send_request(device_id, "cron.run", {"jobId": job_id}, timeout=15.0)
        rpc = _rpc_payload(result)
        if rpc.get("error"):
            return {"success": False, "error": rpc.get("error")}
        return {"success": True, "result": rpc}
    except Exception as e:
        logger.error(f"[cron.run] {e}")
        return {"success": False, "error": str(e)}


@router.get("/{job_id}/runs")
async def cron_runs(job_id: str, device_id: str = None, request: Request = None):
    """获取 cron 任务运行历史"""
    if not request:
        return {"success": False, "error": "device_id required", "runs": []}

    try:
        device_id = await _resolve_device_id(device_id, request)
        if not device_id:
            return {"success": False, "error": "device_id required", "runs": []}

        db = get_db()
        await _require_user_device(db, request, device_id)

        result = await manager.send_request(device_id, "cron.runs", {"jobId": job_id}, timeout=15.0)
        rpc = _rpc_payload(result)
        if rpc.get("error"):
            return {"success": False, "error": rpc.get("error"), "runs": []}
        runs = rpc.get("runs") if isinstance(rpc.get("runs"), list) else []
        return {"success": True, "runs": runs}
    except Exception as e:
        logger.error(f"[cron.runs] {e}")
        return {"success": False, "error": str(e), "runs": []}
