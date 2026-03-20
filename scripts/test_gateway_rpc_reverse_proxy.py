#!/usr/bin/env python3
"""
PocketClaw 反代链路 Gateway RPC 测试脚本

默认模式（推荐）:
  - 连接 /devices/{device_id}/rpc/ws?token=...
  - 预绑定设备后可直接调用 RPC（无需再 connect）

可选模式:
  - 连接 /rpc?token=...
  - 需先发送 method=connect + params.deviceId 绑定设备

用法示例:
  python3 scripts/test_gateway_rpc_reverse_proxy.py

环境变量（可覆盖默认值）:
  RPC_PROXY_HOST        默认 127.0.0.1
  RPC_PROXY_PORT        默认 18789
  RPC_PROXY_TOKEN       登录 token（必填）
  RPC_PROXY_DEVICE_ID   设备 ID（PATH 模式必填）
  RPC_PROXY_MODE        path 或 generic（默认 path）
"""

import json
import os
import time
import uuid

import websocket


HOST = os.getenv("RPC_PROXY_HOST", "127.0.0.1")
PORT = int(os.getenv("RPC_PROXY_PORT", "18789"))
TOKEN = os.getenv("RPC_PROXY_TOKEN", "").strip()
DEVICE_ID = os.getenv("RPC_PROXY_DEVICE_ID", "").strip()
MODE = os.getenv("RPC_PROXY_MODE", "path").strip().lower()  # path | generic


def _recv_json(ws, timeout=15):
    ws.settimeout(timeout)
    raw = ws.recv()
    if not raw:
        return {}
    return json.loads(raw)


def build_url():
    if MODE == "generic":
        return f"ws://{HOST}:{PORT}/rpc?token={TOKEN}"
    if not DEVICE_ID:
        raise ValueError("PATH 模式必须设置 RPC_PROXY_DEVICE_ID")
    return f"ws://{HOST}:{PORT}/devices/{DEVICE_ID}/rpc/ws?token={TOKEN}"


def connect_if_needed(ws):
    """generic 模式需要先 connect；path 模式不需要。"""
    if MODE != "generic":
        return True

    req_id = "connect-" + uuid.uuid4().hex[:8]
    req = {
        "type": "req",
        "id": req_id,
        "method": "connect",
        "params": {
            "deviceId": DEVICE_ID,
            "auth": {"token": TOKEN},
        },
    }
    ws.send(json.dumps(req, ensure_ascii=False))

    deadline = time.time() + 15
    while time.time() < deadline:
        frame = _recv_json(ws, timeout=15)
        if frame.get("type") == "event":
            continue
        if frame.get("type") == "res" and frame.get("id") == req_id:
            if frame.get("ok"):
                print("✅ connect 成功")
                return True
            print(f"❌ connect 失败: {frame.get('error')}")
            return False
    print("❌ connect 超时")
    return False


def rpc_call(ws, method, params=None, timeout=20):
    if params is None:
        params = {}

    req_id = "rpc-" + uuid.uuid4().hex[:8]
    req = {
        "type": "req",
        "id": req_id,
        "method": method,
        "params": params,
    }
    ws.send(json.dumps(req, ensure_ascii=False))

    deadline = time.time() + timeout
    while time.time() < deadline:
        frame = _recv_json(ws, timeout=timeout)
        if frame.get("type") == "event":
            continue
        if frame.get("type") == "res" and frame.get("id") == req_id:
            if frame.get("ok"):
                return frame.get("payload", {})
            return {"error": frame.get("error")}
    return {"error": "timeout"}


def run_smoke():
    if not TOKEN:
        raise ValueError("请先设置 RPC_PROXY_TOKEN")
    if MODE == "generic" and not DEVICE_ID:
        raise ValueError("GENERIC 模式必须设置 RPC_PROXY_DEVICE_ID（用于 connect.deviceId）")

    url = build_url()
    print(f"📡 URL: {url}")
    print(f"🧭 MODE: {MODE}")

    ws = websocket.create_connection(url, timeout=15)
    try:
        if not connect_if_needed(ws):
            return

        tests = [
            ("skills.status", {}),
            ("sessions.list", {}),
            ("channels.status", {}),
        ]
        for method, params in tests:
            print(f"\n📋 {method}")
            result = rpc_call(ws, method, params, timeout=25)
            print(json.dumps(result, ensure_ascii=False, indent=2)[:1500])
    finally:
        ws.close()


if __name__ == "__main__":
    run_smoke()
