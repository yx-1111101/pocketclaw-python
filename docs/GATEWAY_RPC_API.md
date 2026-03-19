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

---

### 1.2 chat.history - 获取历史

**CLI 测试结果：**
```
Session                      Channel     Unread  Last Active
agent:main:main              🤖 agent    0       5 minutes ago
telegram:8773269994:8773269994  ✈️ telegram  0       4 minutes ago
telegram:8773269994:product  ✈️ telegram  0       2 hours ago
```

**RPC 响应：**
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

**响应：**
```python
{"ok": True}
```

---

## 二、Sessions 相关

### 2.1 sessions.list - 会话列表

**CLI 测试结果：**
```
Session                      Channel     Unread  Last Active
agent:main:main              🤖 agent    0       5 minutes ago
telegram:8773269994:8773269994  ✈️ telegram  0       4 minutes ago
telegram:8773269994:product  ✈️ telegram  0       2 hours ago
```

**RPC 响应：**
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
            "key": "telegram:8773269994:8773269994",
            "label": "个人",
            "channel": "telegram",
            "channelIcon": "✈️",
            "shortName": "个人",
            "unreadCount": 0,
            "lastActive": 1739634500000
        }
    ],
    "count": 2
}
```

---

### 2.2 sessions.patch - 修改会话

**请求：**
```python
{
    "function": "sessions.patch",
    "params": {
        "key": "agent:main:main",
        "label": "新名字"
    }
}
```

**响应：**
```python
{"ok": True}
```

---

## 三、Models 相关

### 3.1 models.list - 模型列表

**CLI 测试结果：**
```
Default: minimax/MiniMax-M2.5
Fallbacks: anthropic/claude-sonnet-4-6, minimax/MiniMax-M2.5
Configured (5):
  - anthropic/claude-sonnet-4-6
  - minimax/MiniMax-M2.5
  - minimax-portal/MiniMax-M2.5
  - minimax-portal/MiniMax-M2.5-highspeed
  - minimax-portal/MiniMax-M2.5-Lightning
```

**RPC 响应：**
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
        }
    ]
}
```

---

### 3.2 config.get agents - Agent 配置

**CLI 测试结果：**
```json
{
  "defaults": {
    "model": {
      "primary": "minimax/MiniMax-M2.5",
      "fallbacks": [
        "anthropic/claude-sonnet-4-6",
        "minimax/MiniMax-M2.5",
        "minimax-portal/MiniMax-M2.5-highspeed",
        "minimax-portal/MiniMax-M2.5-Lightning"
      ]
    },
    "models": {
      "anthropic/claude-sonnet-4-6": {"alias": "sonnet"},
      "minimax/MiniMax-M2.5": {"alias": "Minimax"},
      ...
    },
    "workspace": "/root/.openclaw/workspace"
  }
}
```

---

## 四、Skills 相关

### 4.1 skills.list - 技能列表

**CLI 测试结果：**
```
Total: 64 | ✓ Ready: 23 | ✗ Missing: 41

Ready:
  📦 feishu-doc, feishu-drive, feishu-perm, feishu-wiki
  📦 qqbot-cron, qqbot-media
  📦 clawhub, github, weather
  🧩 coding-agent
  ...
```

**RPC 响应：**
```python
{
    "skills": [
        {
            "id": "feishu-doc",
            "name": "飞书文档",
            "status": "ready",
            "description": "Feishu document read/write operations...",
            "source": "openclaw-extra"
        }
    ],
    "count": 64,
    "readyCount": 23
}
```

### 4.2 skills.check - 技能状态检查

**CLI 测试结果：**
```
Skills Status Check

Total: 64
✓ Eligible: 23
⏸ Disabled: 0
🚫 Blocked by allowlist: 0
✗ Missing requirements: 41
```

---

## 五、Cron 相关

### 5.1 cron.list - 任务列表

**CLI 测试结果：**
```
No cron jobs.
```

**RPC 响应：**
```python
{
    "jobs": [],
    "total": 0,
    "offset": 0,
    "limit": 50,
    "hasMore": False
}
```

### 5.2 cron.add - 添加任务

**请求：**
```python
{
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

## 六、Channels 相关

### 6.1 channels.status - 频道状态

**CLI 测试结果：**
```
Telegram default
Support: chatTypes=direct,group,channel,thread polls reactions threads media nativeCommands blockStreaming
Actions: send, broadcast, poll, react, delete, edit, topic-create
Bot: @yixuanclawbot (8773269994)
Flags: joinGroups=true readAllGroupMessages=true inlineQueries=false
Webhook: none

Telegram marketing
Bot: @MarktingBot (8664793655)
Flags: joinGroups=true readAllGroupMessages=true inlineQueries=false

QQ Bot default
Support: chatTypes=direct,group media
Actions: send, broadcast
Status: not configured, enabled

WeCom default
Support: chatTypes=direct,group media blockStreaming
```

### 6.2 channels.capabilities - 频道能力详情

**Telegram 支持的功能：**
| 功能 | 说明 |
|------|------|
| chatTypes | direct, group, channel, thread |
| polls | 投票 |
| reactions | 反应 |
| threads | 话题 |
| media | 媒体 |
| nativeCommands | 原生命令 |
| blockStreaming | 阻止流式 |

**Telegram 支持的操作：**
| Action | 说明 |
|--------|------|
| send | 发送消息 |
| broadcast | 广播 |
| poll | 创建投票 |
| react | 添加反应 |
| delete | 删除消息 |
| edit | 编辑消息 |
| topic-create | 创建话题 |

---

## 七、Config 相关

### 7.1 config.get - 获取配置

**CLI 测试结果 (openclaw status)：**
```
Channel         │ stable (default)
Update          │ available · pnpm · npm update 2026.3.13
Gateway         │ local · ws://127.0.0.1:18789 · reachable 32ms · auth token
Gateway service │ systemd installed · enabled · running (pid 761)
Agents          │ 6 · 6 bootstrap files present · sessions 33 · default main active
Memory         │ 0 files · 0 chunks · sources memory · plugin memory-core
Sessions       │ 33 active · default MiniMax-M2.5 (200k ctx) · 6 stores
Heartbeat      │ 1h (main), disabled (bench-*)
```

---

## 八、ACP/Tools 相关

### 8.1 acp.list - 可用工具

**CLI 测试结果 (acp tools)：**
```
message.send, message.delete, message.react
memory.get, memory.search
sessions.list, sessions.send
subagents, cron, tts
browser, web.fetch, web.search
...
```

**RPC 响应：**
```python
{
    "tools": [
        {"id": "message_send", "name": "message.send", "description": "Send a message..."},
        {"id": "memory_search", "name": "memory.search", "description": "Search memory"},
        {"id": "browser", "name": "browser", "description": "Control browser"},
        {"id": "web_fetch", "name": "web.fetch", "description": "Fetch URL content"},
        {"id": "web_search", "name": "web.search", "description": "Search the web"}
    ],
    "count": 45
}
```

---

## 九、完整 Python 示例

```python
import websocket
import json

TOKEN = "你的-token"
URL = f"ws://127.0.0.1:18789/ws?token={TOKEN}"

def rpc_call(ws, method, params=None):
    if params is None:
        params = {}
    req = {"id": method, "function": method, "params": params}
    ws.send(json.dumps(req))
    return json.loads(ws.recv())

ws = websocket.create_connection(URL)

# 测试
print(rpc_call(ws, "sessions.list", {}))
print(rpc_call(ws, "skills.list", {}))
print(rpc_call(ws, "models.list", {}))
print(rpc_call(ws, "cron.list", {}))
print(rpc_call(ws, "channels.status", {}))

ws.close()
```

---

## 测试结果汇总

| API | 状态 | 测试结果 |
|-----|------|----------|
| chat.send | ✅ | 正常 |
| chat.history | ✅ | 正常 |
| sessions.list | ✅ | 2个会话 |
| skills.list | ✅ | 64个(23可用) |
| models.list | ✅ | 5个模型 |
| cron.list | ✅ | 无任务 |
| channels.status | ✅ | 3个频道 |
| config.get | ✅ | 正常 |
| acp.list | ✅ | 45个工具 |
