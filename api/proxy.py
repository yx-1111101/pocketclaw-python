"""网关代理 API 路由"""
import base64
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.core.security import parse_user_from_auth_header
from app.core.supabase import get_db
from app.core.websocket import manager

router = APIRouter(prefix="/devices", tags=["网关"])


def is_online(device: dict) -> bool:
    if not device:
        return False
    last_seen_ms = _to_epoch_ms(device.get("last_seen"))
    if not last_seen_ms:
        return False
    return datetime.now(timezone.utc).timestamp() * 1000 - last_seen_ms < 5 * 60 * 1000


def _to_epoch_ms(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        num = float(value)
        if num <= 0:
            return 0
        return int(num if num > 10_000_000_000 else num * 1000)
    text = str(value).strip()
    if not text:
        return 0
    try:
        num = float(text)
        return int(num if num > 10_000_000_000 else num * 1000)
    except Exception:
        pass
    try:
        normalized = text.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp() * 1000)
    except Exception:
        return 0


def _require_token_user_id(request: Request) -> str:
    user_id, err = parse_user_from_auth_header(request.headers.get("Authorization", ""))
    if err:
        raise HTTPException(status_code=401, detail=err)
    return str(user_id or "").strip()


async def _fetch_single(db, table: str, filters: dict):
    rows = await db.get(table, filters)
    if isinstance(rows, dict) and rows.get("error"):
        raise HTTPException(status_code=500, detail=f"查询 {table} 失败: {rows['error']}")
    if not rows or isinstance(rows, dict):
        return None
    return rows[0]


async def _require_user(db, request: Request):
    user_id = _require_token_user_id(request)
    user = await _fetch_single(db, "users", {"user_id": user_id})
    if not user:
        raise HTTPException(status_code=401, detail="token 对应用户不存在")
    return user


async def _require_user_device(db, request: Request, device_id: str):
    """验证用户是否有权访问设备 - 只查绑定表"""
    user = await _require_user(db, request)
    owner_user_id = str(user.get("user_id") or "").strip()
    if not owner_user_id:
        raise HTTPException(status_code=500, detail="用户数据异常（缺少 user_id）")
    
    # 直接查绑定关系，隐含验证设备存在
    binding = await _fetch_single(db, "device_bindings", {"user_id": owner_user_id, "device_id": device_id})
    if not binding:
        raise HTTPException(status_code=403, detail="无权访问该设备")
    
    # 设备 ID 优先用 binding 中的
    resolved_device_id = str(binding.get("device_id") or device_id).strip()
    
    return user, {"device_id": resolved_device_id}, binding


@router.get("/{device_id}/status")
async def get_status(device_id: str, request: Request):
    db = get_db()
    _, device, _ = await _require_user_device(db, request, device_id)
    device_id_str = device.get("device_id", "")
    ws_online = manager.is_connected(device_id_str)
    return {
        "ok": True,
        "device": {
            "device_id": device_id_str,
            "status": "online" if (is_online(device) or ws_online) else device.get("status", "offline"),
            "ws_connected": ws_online,
            "last_seen": device.get("last_seen", 0),
        },
    }


@router.get("/{device_id}")
async def get_device(device_id: str, request: Request):
    db = get_db()
    _, device, _ = await _require_user_device(db, request, device_id)
    device_id_str = device.get("device_id", "")
    ws_online = manager.is_connected(device_id_str)
    return {
        "device_id": device_id_str,
        "name": device.get("name", "我的盒子"),
        "public_url": device.get("public_url", ""),
        "status": "online" if (is_online(device) or ws_online) else device.get("status", "offline"),
        "last_seen": device.get("last_seen", 0),
    }


@router.delete("/{device_id}/bind")
async def unbind_device(device_id: str, request: Request):
    db = get_db()
    user, device, _ = await _require_user_device(db, request, device_id)
    owner_user_id = str(user.get("user_id") or "").strip()
    resolved_device_id = str(device.get("device_id") or device_id).strip()
    deleted = await db.delete("device_bindings", {"user_id": owner_user_id, "device_id": resolved_device_id})
    if isinstance(deleted, dict) and deleted.get("error"):
        return JSONResponse({"ok": False, "error": f"解绑失败: {deleted['error']}"}, status_code=500)
    return {"ok": True}


@router.get("/{device_id}/metrics")
async def get_device_metrics(device_id: str, request: Request):
    db = get_db()
    await _require_user_device(db, request, device_id)
    if manager.is_connected(device_id):
        try:
            result = await manager.send_request(
                device_id, "setup/api/services", method="GET", timeout=10.0,
            )
            return result.get("data", {"cpu": 0, "memory": 0, "uptime": 0})
        except Exception:
            pass
    return {"cpu": 0, "memory": 0, "uptime": 0}


async def _gateway_proxy_impl(device_id: str, path: str, request: Request):
    """通用网关代理：支持 GET/POST/PUT/DELETE，将 HTTP method 透传给设备端。"""
    db = get_db()
    await _require_user_device(db, request, device_id)
    method = request.method
    body = await request.body()
    try:
        data = json.loads(body) if body else {}
    except Exception:
        data = {}

    query_params = dict(request.query_params) if request.query_params else None

    try:
        result = await manager.send_request(
            device_id, path, data,
            method=method,
            query=query_params,
        )
        # send_request 返回 {"status": "success", "request_id": "...", "data": <设备数据>}
        # 设备端二进制内容封装在 data 里：{_file_b64, _content_type, _status}
        inner = result.get("data") if isinstance(result, dict) and "data" in result else result
        if isinstance(inner, dict) and isinstance(inner.get("_file_b64"), str):
            try:
                raw = base64.b64decode(inner.get("_file_b64") or "")
            except Exception:
                raw = b""
            media_type = str(inner.get("_content_type") or "application/octet-stream")
            status = int(inner.get("_status") or 200)
            return Response(content=raw, media_type=media_type, status_code=status)
        return result
    except HTTPException:
        raise


@router.get("/{device_id}/gateway/{path:path}")
async def gateway_proxy_get(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.post("/{device_id}/gateway/{path:path}")
async def gateway_proxy_post(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.put("/{device_id}/gateway/{path:path}")
async def gateway_proxy_put(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.delete("/{device_id}/gateway/{path:path}")
async def gateway_proxy_delete(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.patch("/{device_id}/gateway/{path:path}")
async def gateway_proxy_patch(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.options("/{device_id}/gateway/{path:path}")
async def gateway_proxy_options(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)

@router.head("/{device_id}/gateway/{path:path}")
async def gateway_proxy_head(device_id: str, path: str, request: Request):
    return await _gateway_proxy_impl(device_id, path, request)
