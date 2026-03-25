#!/usr/bin/env python3
"""
OpenClaw Gateway WebSocket RPC 测试脚本

使用方式:
    python3 test_gateway_rpc.py

需要先安装:
    pip install websocket-client
"""

import os
import websocket
import json
import time
import uuid

# Gateway 配置 (set via environment variables or edit below for local testing)
GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "18789"))
TOKEN = os.getenv("GATEWAY_TOKEN", "")

URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws?token={TOKEN}"


def _recv_json(ws, timeout=10):
    ws.settimeout(timeout)
    raw = ws.recv()
    if not raw:
        return {}
    return json.loads(raw)


def connect_gateway(ws):
    """按新版 Gateway 协议完成 connect 握手"""
    # 等待网关发 connect.challenge（不强依赖 nonce；token 鉴权无需 device.nonce）
    try:
        first = _recv_json(ws, timeout=5)
        if first.get("type") == "event" and first.get("event") == "connect.challenge":
            print(f"🔐 收到挑战: {first.get('payload', {})}")
        elif first:
            print(f"ℹ️  首帧: {first}")
    except Exception:
        pass

    req_id = "connect-" + uuid.uuid4().hex[:8]
    connect_req = {
        "type": "req",
        "id": req_id,
        "method": "connect",
        "params": {
            "minProtocol": 3,
            "maxProtocol": 3,
            "role": "operator",
            "scopes": ["operator.read", "operator.write", "operator.admin"],
            "auth": {"token": TOKEN},
            "client": {
                "id": "openclaw-control-ui",
                "version": "1.0.0",
                "platform": "linux",
                "mode": "ui",
            },
            "caps": [],
            "commands": [],
            "permissions": {},
        },
    }
    ws.send(json.dumps(connect_req, ensure_ascii=False))

    deadline = time.time() + 10
    while time.time() < deadline:
        data = _recv_json(ws, timeout=10)
        if data.get("type") == "event":
            continue
        if data.get("type") == "res" and data.get("id") == req_id:
            if data.get("ok"):
                print("✅ connect 成功")
                return True
            print(f"❌ connect 失败: {data.get('error')}")
            return False
    print("❌ connect 超时")
    return False


def rpc_call(ws, method, params=None, timeout=15):
    """发送 RPC 请求并返回 payload"""
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
        try:
            data = _recv_json(ws, timeout=timeout)
        except Exception as e:
            print(f"❌ 错误: {e}")
            return None

        if data.get("type") == "event":
            continue

        if data.get("type") == "res" and data.get("id") == req_id:
            if data.get("ok"):
                return data.get("payload", {})
            err = data.get("error") or {}
            return {"error": err}

    print(f"❌ {method} 超时")
    return None





def test_sessions():
    """测试 Sessions 相关"""
    print("\n" + "=" * 50)
    print("📋 测试 Sessions API")
    print("=" * 50)

    ws = websocket.create_connection(URL)
    if not connect_gateway(ws):
        ws.close()
        return

    print("\n📋 sessions.list")
    result = rpc_call(ws, "sessions.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1500])

    ws.close()


def test_skills():
    """测试 Skills 相关"""
    print("\n" + "=" * 50)
    print("🛠️  测试 Skills API")
    print("=" * 50)

    ws = websocket.create_connection(URL)
    if not connect_gateway(ws):
        ws.close()
        return

    # skills.status
    print("\n📋 skills.status")
    result = rpc_call(ws, "skills.status", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])

    ws.close()


def test_models():
    """测试 Models 相关"""
    print("\n" + "=" * 50)
    print("🤖 测试 Models API")
    print("=" * 50)

    ws = websocket.create_connection(URL)
    if not connect_gateway(ws):
        ws.close()
        return

    # models.list
    print("\n📋 models.list")
    result = rpc_call(ws, "models.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1500])

    ws.close()


def test_cron():
    """测试 Cron 相关"""
    print("\n" + "=" * 50)
    print("⏰ 测试 Cron API")
    print("=" * 50)

    ws = websocket.create_connection(URL)
    if not connect_gateway(ws):
        ws.close()
        return

    # cron.list
    print("\n📋 cron.list")
    result = rpc_call(ws, "cron.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])

    ws.close()


def test_channels():
    """测试 Channels 相关"""
    print("\n" + "=" * 50)
    print("📱 测试 Channels API")
    print("=" * 50)

    ws = websocket.create_connection(URL)
    if not connect_gateway(ws):
        ws.close()
        return

    # channels.status
    print("\n📋 channels.status")
    result = rpc_call(ws, "channels.status", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])

    ws.close()


def test_config():
    """测试 Config 相关"""
    print("\n" + "=" * 50)
    print("⚙️  测试 Config API")
    print("=" * 50)

    ws = websocket.create_connection(URL)
    if not connect_gateway(ws):
        ws.close()
        return

    # config.get
    print("\n📋 config.get")
    result = rpc_call(ws, "config.get", {"path": "agents.defaults.model"})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:500])

    ws.close()


def test_all():
    """运行所有测试"""
    print("🚀 开始测试 OpenClaw Gateway RPC")
    print(f"📡 URL: {URL}")

    try:
        test_sessions()
        test_skills()
        test_models()
        test_cron()
        test_channels()
        test_config()

        print("\n" + "=" * 50)
        print("✅ 所有测试完成!")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")


if __name__ == "__main__":
    test_all()
