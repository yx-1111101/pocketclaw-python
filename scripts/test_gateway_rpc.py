#!/usr/bin/env python3
"""
OpenClaw Gateway WebSocket RPC 测试脚本

使用方式:
    python3 test_gateway_rpc.py

需要先安装:
    pip install websocket-client
"""

import websocket
import json
import time

# Gateway 配置
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18789
TOKEN = "你的-token"

URL = f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}/ws?token={TOKEN}"


def rpc_call(ws, method, params=None):
    """发送 RPC 请求并返回结果"""
    if params is None:
        params = {}
    
    req = {
        "id": method,
        "function": method,
        "params": params
    }
    
    ws.send(json.dumps(req))
    time.sleep(0.3)
    
    try:
        resp = ws.recv()
        data = json.loads(resp)
        
        # 处理连接挑战
        if data.get("type") == "event" and data.get("event") == "connect.challenge":
            print(f"⚠️  需要认证: {data}")
            return None
            
        return data.get("result", data)
    except Exception as e:
        print(f"❌ 错误: {e}")
        return None


def test_chat():
    """测试 Chat 相关"""
    print("\n" + "="*50)
    print("🗨️  测试 Chat API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
    # chat.send
    print("\n📤 chat.send")
    result = rpc_call(ws, "chat.send", {
        "content": "你好",
        "sessionKey": "agent:main:main"
    })
    print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
    
    # chat.history
    print("\n📥 chat.history")
    result = rpc_call(ws, "chat.history", {"limit": 5})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
    
    ws.close()


def test_sessions():
    """测试 Sessions 相关"""
    print("\n" + "="*50)
    print("📋 测试 Sessions API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
    # sessions.list
    print("\n📋 sessions.list")
    result = rpc_call(ws, "sessions.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1500])
    
    ws.close()


def test_skills():
    """测试 Skills 相关"""
    print("\n" + "="*50)
    print("🛠️  测试 Skills API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
    # skills.list
    print("\n📋 skills.list")
    result = rpc_call(ws, "skills.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    
    ws.close()


def test_models():
    """测试 Models 相关"""
    print("\n" + "="*50)
    print("🤖 测试 Models API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
    # models.list
    print("\n📋 models.list")
    result = rpc_call(ws, "models.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1500])
    
    ws.close()


def test_cron():
    """测试 Cron 相关"""
    print("\n" + "="*50)
    print("⏰ 测试 Cron API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
    # cron.list
    print("\n📋 cron.list")
    result = rpc_call(ws, "cron.list", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:1000])
    
    ws.close()


def test_channels():
    """测试 Channels 相关"""
    print("\n" + "="*50)
    print("📱 测试 Channels API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
    # channels.status
    print("\n📋 channels.status")
    result = rpc_call(ws, "channels.status", {})
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    
    ws.close()


def test_config():
    """测试 Config 相关"""
    print("\n" + "="*50)
    print("⚙️  测试 Config API")
    print("="*50)
    
    ws = websocket.create_connection(URL)
    
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
        test_chat()
        test_sessions()
        test_skills()
        test_models()
        test_cron()
        test_channels()
        test_config()
        
        print("\n" + "="*50)
        print("✅ 所有测试完成!")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")


if __name__ == "__main__":
    test_all()
