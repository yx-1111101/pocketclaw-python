# OpenClaw Gateway WebSocket RPC 接口文档 (Python)

> 基于 OpenClaw 2026.3.7 实际测试整理

## 连接方式

```python
import websocket

ws = websocket.create_connection(
    f"ws://<host>:18789/ws?token=<token>",
    header={"Authorization": "Bearer <token>"}
)
```

**Python 请求示例：**
```python
import websocket
import json

def rpc_call(ws, method, params={}):
    req = {"id": method, "function": method, "params": params}
    ws.send(json.dumps(req))
    return json.loads(ws.recv())
```

---

## 一、Chat 相关

### 1.1 chat.send - 发送消息

**请求：**
```python
{
    "id": "send_msg",
    "function": "chat.send",
    "params": {
        "content": "你好",
        "sessionKey": "agent:main:main"
    }
}
```

**响应：**
```python
{
    "runId": "run_xxx",
    "status": "started"
}
```

**参数说明：**
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| content | string | 是 | 消息内容 |
| sessionKey | string | 否 | 会话Key，默认 agent:main:main |
| idempotencyKey | string | 否 | 幂等Key |

---

### 1.2 chat.history - 获取历史

**请求：**
```python
{
    "id": "history",
    "function": "chat.history",
    "params": {
        "limit": 10,
        "sessionKey": "agent:main:main"
    }
}
```

**响应：**
```python
{
    "messages": [
        {
            "id": "msg_xxx",
            "role": "user",
            "content": "你好",
            "time": 1739634000000
        },
        {
            "id": "msg_xxx",
            "role": "assistant",
            "content": "你好！有什么可以帮助你的吗？",
            "time": 1739634015000
        }
    ],
    "hasMore": False
}
```

---

### 1.3 chat.abort - 终止对话

**请求：**
```python
{
    "id": "abort",
    "function": "chat.abort",
    "params": {
        "runId": "run_xxx"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

### 1.4 chat.inject - 注入消息

**请求：**
```python
{
    "id": "inject",
    "function": "chat.inject",
    "params": {
        "role": "user",
        "content": "Hello"
    }
}
```

**响应：**
```python
{
    "id": "msg_xxx"
}
```

---

## 二、Sessions 相关

### 2.1 sessions.list - 会话列表

**请求：**
```python
{
    "id": "sessions",
    "function": "sessions.list",
    "params": {}
}
```

**响应：**
```python
{
    "sessions": [
        {
            "key": "agent:main:main",
            "label": "main",
            "channel": "agent",
            "channelIcon": "🤖",
            "shortName": "main",
            "unreadCount": 0,
            "lastActive": 1739634600000
        },
        {
            "key": "telegram:110xxx:12345",
            "label": "个人",
            "channel": "telegram",
            "channelIcon": "✈️",
            "shortName": "个人",
            "unreadCount": 0,
            "lastActive": 1739634500000
        },
        {
            "key": "telegram:110xxx:marketing",
            "label": "市场群",
            "channel": "telegram",
            "channelIcon": "✈️",
            "shortName": "市场群",
            "unreadCount": 3,
            "lastActive": 1739634000000
        }
    ],
    "count": 3
}
```

---

### 2.2 sessions.patch - 修改会话

**请求：**
```python
{
    "id": "patch",
    "function": "sessions.patch",
    "params": {
        "key": "agent:main:main",
        "label": "新名字"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

## 三、Cron 相关

### 3.1 cron.list - 任务列表

**请求：**
```python
{
    "id": "cron_list",
    "function": "cron.list",
    "params": {}
}
```

**响应：**
```python
{
    "jobs": [],
    "total": 0,
    "offset": 0,
    "limit": 50,
    "hasMore": False,
    "nextOffset": None
}
```

---

### 3.2 cron.add - 添加任务

**请求：**
```python
{
    "id": "cron_add",
    "function": "cron.add",
    "params": {
        "name": "每日提醒",
        "schedule": "0 9 * * *",
        "message": "该起床了！"
    }
}
```

**响应：**
```python
{
    "ok": True,
    "jobId": "cron_xxx"
}
```

---

### 3.3 cron.edit - 编辑任务

**请求：**
```python
{
    "id": "cron_edit",
    "function": "cron.edit",
    "params": {
        "jobId": "cron_xxx",
        "name": "新名字",
        "schedule": "0 10 * * *"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

### 3.4 cron.delete - 删除任务

**请求：**
```python
{
    "id": "cron_del",
    "function": "cron.delete",
    "params": {
        "jobId": "cron_xxx"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

### 3.5 cron.run - 执行任务

**请求：**
```python
{
    "id": "cron_run",
    "function": "cron.run",
    "params": {
        "jobId": "cron_xxx"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

## 四、Skills 相关

### 4.1 skills.list - 技能列表

**请求：**
```python
{
    "id": "skills",
    "function": "skills.list",
    "params": {}
}
```

**响应：**
```python
{
    "skills": [
        {
            "id": "github",
            "name": "GitHub",
            "status": "ready",
            "description": "Interacts with GitHub using gh CLI"
        },
        {
            "id": "weather",
            "name": "Weather", 
            "status": "ready",
            "description": "Get weather forecasts"
        },
        {
            "id": "feishu-doc",
            "name": "飞书文档",
            "status": "ready",
            "description": "Feishu document read/write operations"
        },
        {
            "id": "qqbot-cron",
            "name": "QQ提醒",
            "status": "ready",
            "description": "QQ Bot 智能提醒技能"
        }
    ],
    "count": 23
}
```

**状态说明：**
| status | 说明 |
|--------|------|
| ready | 可用 |
| loading | 加载中 |
| missing | 缺少依赖 |

---

### 4.2 skills.enable - 启用技能

**请求：**
```python
{
    "id": "enable_skill",
    "function": "skills.enable",
    "params": {
        "skillId": "github"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

### 4.3 skills.disable - 禁用技能

**请求：**
```python
{
    "id": "disable_skill",
    "function": "skills.disable",
    "params": {
        "skillId": "github"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

### 4.4 skills.install - 安装技能

**请求：**
```python
{
    "id": "install_skill",
    "function": "skills.install",
    "params": {
        "repo": "openclaw/skills-weather"
    }
}
```

**响应：**
```python
{
    "ok": True,
    "skillId": "weather"
}
```

---

## 五、Channels 相关

### 5.1 channels.status - 频道状态

**请求：**
```python
{
    "id": "channels",
    "function": "channels.status",
    "params": {}
}
```

**响应：**
```python
{
    "chat": {
        "telegram": ["default", "marketing", "product"],
        "qqbot": [],
        "wecom": ["default"],
        "adp-openclaw": ["default"],
        "ddingtalk": []
    },
    "auth": [
        {
            "id": "openrouter:default",
            "provider": "openrouter",
            "type": "api_key",
            "isExternal": False
        },
        {
            "id": "google:default", 
            "provider": "google",
            "type": "api_key",
            "isExternal": False
        },
        {
            "id": "anthropic:default",
            "provider": "anthropic",
            "type": "token",
            "isExternal": False
        }
    ],
    "usage": {
        "updatedAt": 1773924075790,
        "providers": [
            {
                "provider": "anthropic",
                "displayName": "Claude",
                "windows": [],
                "error": "HTTP 403: OAuth token does not meet scope"
            }
        ]
    }
}
```

---

### 5.2 channels.login - 登录频道

**请求：**
```python
{
    "id": "login",
    "function": "web.login.qrcode",
    "params": {
        "channel": "telegram"
    }
}
```

**响应：**
```python
{
    "qrcode": "https://...",
    "qrcodeId": "xxx"
}
```

---

### 5.3 web.login.status - 登录状态

**请求：**
```python
{
    "id": "login_status",
    "function": "web.login.status",
    "params": {
        "channel": "telegram",
        "qrcodeId": "xxx"
    }
}
```

**响应：**
```python
{
    "status": "pending"  # 或 "success", "failed"
}
```

---

## 六、Models 相关

### 6.1 models.list - 模型列表

**请求：**
```python
{
    "id": "models",
    "function": "models.list",
    "params": {}
}
```

**响应：**
```python
{
    "count": 5,
    "models": [
        {
            "key": "minimax/MiniMax-M2.5",
            "name": "MiniMax M2.5",
            "input": "text",
            "contextWindow": 200000,
            "local": False,
            "available": True,
            "tags": ["default", "fallback#2", "configured", "alias:Minimax"]
        },
        {
            "key": "anthropic/claude-sonnet-4-6",
            "name": "Claude Sonnet 4.6",
            "input": "text+image",
            "contextWindow": 200000,
            "local": False,
            "available": True,
            "tags": ["fallback#1", "configured"]
        },
        {
            "key": "openai/gpt-4o",
            "name": "GPT-4o",
            "input": "text+image",
            "contextWindow": 128000,
            "local": False,
            "available": True,
            "tags": []
        }
    ]
}
```

---

## 七、Config 相关

### 7.1 config.get - 获取配置

**请求：**
```python
{
    "id": "config_get",
    "function": "config.get",
    "params": {
        "path": "agents.defaults.model"
    }
}
```

**响应：**
```python
{
    "value": "minimax/MiniMax-M2.5"
}
```

---

### 7.2 config.set - 设置配置

**请求：**
```python
{
    "id": "config_set",
    "function": "config.set",
    "params": {
        "path": "agents.defaults.model",
        "value": "anthropic/claude-sonnet-4-6"
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

### 7.3 config.patch - 补丁配置

**请求：**
```python
{
    "id": "config_patch",
    "function": "config.patch",
    "params": {
        "path": "agents.defaults",
        "value": {
            "model": "anthropic/claude-sonnet-4-6"
        }
    }
}
```

**响应：**
```python
{
    "ok": True
}
```

---

## 八、Tools 相关 (ACP)

### 8.1 acp.list - 可用工具列表

**请求：**
```python
{
    "id": "acp_list",
    "function": "acp.list",
    "params": {}
}
```

**响应：**
```python
{
    "tools": [
        {
            "id": "message_send",
            "name": "message.send",
            "description": "Send a message via channel"
        },
        {
            "id": "memory_search",
            "name": "memory.search", 
            "description": "Search memory"
        }
    ]
}
```

---

## 九、完整 Python 示例

```python
import websocket
import json
import asyncio

class GatewayClient:
    def __init__(self, url, token):
        self.url = f"{url}/ws?token={token}"
        self.ws = None
        
    def connect(self):
        self.ws = websocket.create_connection(self.url)
        
    def call(self, method, params=None):
        if params is None:
            params = {}
        req = {"id": method, "function": method, "params": params}
        self.ws.send(json.dumps(req))
        resp = json.loads(self.ws.recv())
        return resp.get("result", resp)
    
    # 快捷方法
    def send_message(self, content, session_key="agent:main:main"):
        return self.call("chat.send", {"content": content, "sessionKey": session_key})
    
    def get_history(self, limit=50, session_key="agent:main:main"):
        return self.call("chat.history", {"limit": limit, "sessionKey": session_key})
    
    def list_sessions(self):
        return self.call("sessions.list", {})
    
    def list_skills(self):
        return self.call("skills.list", {})
    
    def list_models(self):
        return self.call("models.list", {})
    
    def list_crons(self):
        return self.call("cron.list", {})
    
    def channel_status(self):
        return self.call("channels.status", {})
    
    def get_config(self, path):
        return self.call("config.get", {"path": path})


# 使用
client = GatewayClient("ws://192.168.1.100:18789", "your-token")
client.connect()

# 发送消息
result = client.send_message("你好")
print(result)

# 获取历史
history = client.get_history()
print(history)

# 会话列表
sessions = client.list_sessions()
print(sessions)

# 技能列表
skills = client.list_skills()
print(skills)
```

---

## 错误响应格式

```python
{
    "error": {
        "code": 500,
        "message": "Internal server error",
        "data": {}
    }
}
```

**常见错误码：**
| code | 说明 |
|------|------|
| 400 | 参数错误 |
| 401 | 未授权 |
| 404 | 方法不存在 |
| 500 | 服务器错误 |
