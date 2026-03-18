# PocketClaw Cloud API 开发文档

## 架构概览

```
┌─────────────┐     HTTP      ┌─────────────────┐    WebSocket     ┌──────────┐
│   小程序     │ ──────────► │  PocketClaw    │ ◄─────────────► │  设备    │
│ (客户端)    │              │     Cloud       │                 │ Gateway  │
│             │              │   (本服务)      │                 │          │
└─────────────┘              └─────────────────┘                 └──────────┘
```

## 数据流说明

| 方向 | 协议 | 说明 |
|------|------|------|
| 小程序 → Cloud | HTTP REST | 小程序调用 REST API |
| Cloud → Gateway | WebSocket RPC | Cloud 转发请求到设备 |
| Gateway → Cloud | WebSocket | 设备推送消息给 Cloud |
| Cloud → 小程序 | HTTP / WebSocket | 推送消息给小程序 |

---

## 一、小程序 API 接口

### 1. 频道管理 (Channels)

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /devices/{deviceId}/channels` | GET | 获取频道列表 |
| `POST /devices/{deviceId}/channels/{channelId}` | POST | 配置频道 |
| `PATCH /devices/{deviceId}/channels/{channelId}` | PATCH | 更新频道配置 |
| `DELETE /devices/{deviceId}/channels/{channelId}` | DELETE | 删除频道配置 |

**请求示例：**
```bash
GET /devices/device-123/channels
```

**响应：**
```json
{
  "success": true,
  "channels": [
    {
      "id": "telegram",
      "name": "Telegram",
      "enabled": true,
      "connected": true,
      "config": {}
    },
    {
      "id": "feishu",
      "name": "飞书",
      "enabled": false,
      "connected": false,
      "config": {}
    }
  ]
}
```

### 2. 模型管理 (Models)

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /models/platform` | GET | 获取平台模型列表 |
| `PATCH /models/platform/{modelId}` | PATCH | 启用/禁用平台模型 |
| `GET /models/custom` | GET | 获取自定义模型列表 |
| `POST /models/custom` | POST | 添加自定义模型 |
| `PATCH /models/custom/{modelId}` | PATCH | 更新自定义模型 |
| `DELETE /models/custom/{modelId}` | DELETE | 删除自定义模型 |

**请求示例：**
```bash
GET /models/platform
```

**响应：**
```json
{
  "success": true,
  "models": [
    { "id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI", "enabled": true },
    { "id": "claude-sonnet", "name": "Claude Sonnet", "provider": "Anthropic", "enabled": true }
  ]
}
```

### 3. MCP 服务管理

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /mcp/services` | GET | 获取 MCP 服务列表 |
| `POST /mcp/services` | POST | 添加 MCP 服务 |
| `PATCH /mcp/services/{serviceId}` | PATCH | 更新 MCP 服务 |
| `DELETE /mcp/services/{serviceId}` | DELETE | 删除 MCP 服务 |

### 4. 用户信息

| 接口 | 方法 | 说明 |
|------|------|------|
| `GET /user/profile` | GET | 获取用户信息 |
| `PATCH /user/profile` | PATCH | 更新用户信息 |

---

## 二、PocketClaw Cloud → Gateway RPC 调用

当小程序调用 API 时，Cloud 需要将请求转发到设备的 Gateway。

### 2.1 RPC 转发机制

```python
# 伪代码示例
async def forward_to_gateway(device_id: str, method: str, params: dict):
    # 1. 获取设备的 WebSocket 连接
    ws = await get_device_connection(device_id)
    
    # 2. 发送 RPC 请求
    request = {
        "id": generate_request_id(),
        "function": method,
        "params": params
    }
    await ws.send(json.dumps(request))
    
    # 3. 等待响应
    response = await wait_for_response(request["id"], timeout=30)
    return response
```

### 2.2 Channel 相关 RPC

| RPC 方法 | 参数 | 说明 |
|----------|------|------|
| `channels.status` | - | 获取频道状态 |
| `channels.configure` | `{channelId, config}` | 配置频道 |
| `web.login.qrcode` | `{channel}` | 获取登录二维码 |
| `web.login.status` | `{channel, qrcodeId}` | 检查登录状态 |

### 2.3 Model 相关 RPC

| RPC 方法 | 参数 | 说明 |
|----------|------|------|
| `models.list` | - | 获取模型列表 |
| `models.enable` | `{modelId}` | 启用模型 |
| `models.disable` | `{modelId}` | 禁用模型 |
| `models.add_custom` | `{model}` | 添加自定义模型 |
| `models.remove_custom` | `{modelId}` | 删除自定义模型 |

### 2.4 MCP 相关 RPC

| RPC 方法 | 参数 | 说明 |
|----------|------|------|
| `mcp.services.list` | - | 获取 MCP 服务列表 |
| `mcp.services.add` | `{name, command, args, env}` | 添加服务 |
| `mcp.services.remove` | `{serviceId}` | 删除服务 |
| `mcp.services.start` | `{serviceId}` | 启动服务 |
| `mcp.services.stop` | `{serviceId}` | 停止服务 |

### 2.5 会话相关 RPC（已实现）

| RPC 方法 | 说明 |
|----------|------|
| `chat.send` | 发送消息 |
| `chat.history` | 获取历史 |
| `chat.abort` | 终止对话 |
| `sessions.list` | 会话列表 |
| `sessions.create` | 创建会话 |
| `sessions.delete` | 删除会话 |

### 2.6 Cron 相关 RPC（已实现）

| RPC 方法 | 说明 |
|----------|------|
| `cron.list` | 任务列表 |
| `cron.add` | 添加任务 |
| `cron.edit` | 编辑任务 |
| `cron.delete` | 删除任务 |
| `cron.run` | 执行任务 |

---

## 三、设备端响应处理

### 3.1 WebSocket 消息推送

设备 Gateway 可能主动推送消息给 Cloud：

```python
# 设备端推送消息
{
    "event": "chat",
    "sessionKey": "main",
    "message": {
        "role": "assistant",
        "content": "你好！"
    }
}
```

### 3.2 Cloud 推送给小程序

Cloud 收到设备推送后，通过以下方式通知小程序：

1. **HTTP 长轮询** - 小程序定期拉取
2. **WebSocket 推送** - 实时推送（推荐）

---

## 四、数据流示例

### 4.1 用户发送消息

```
1. 小程序 POST /devices/{id}/chat/history?sessionKey=main
                    ↓
2. Cloud 调用 Gateway WebSocket
                    ↓
3. Gateway 执行 chat.history RPC
                    ↓
4. 返回消息列表给 Cloud
                    ↓
5. Cloud 返回给小程序
```

### 4.2 配置 Telegram 频道

```
1. 小程序 POST /devices/{id}/channels/telegram
   Body: {"botToken": "xxx"}
                    ↓
2. Cloud 验证参数
                    ↓
3. Cloud 调用 Gateway WebSocket
   RPC: channels.configure
   Params: {channelId: "telegram", config: {...}}
                    ↓
4. Gateway 配置 Telegram Bot
                    ↓
5. 返回配置结果
                    ↓
6. Cloud 保存配置，返回给小程序
```

---

## 五、错误处理

### 5.1 错误码定义

| 错误码 | 说明 |
|--------|------|
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 408 | 请求超时 |
| 500 | 服务器内部错误 |
| 502 | 网关错误 |
| 503 | 服务不可用 |

### 5.2 错误响应格式

```json
{
  "success": false,
  "error": {
    "code": 500,
    "message": "Internal server error",
    "detail": "..."
  }
}
```

---

## 六、安全认证

### 6.1 小程序认证

- 用户登录获取 JWT Token
- 请求头携带：`Authorization: Bearer <token>`

### 6.2 Cloud → Gateway 认证

- Gateway Token 验证
- 设备绑定关系验证

---

## 七、需要实现的核心接口

| 模块 | 接口数 | 优先级 |
|------|--------|--------|
| 频道管理 | 4 | P0 |
| 模型管理 | 6 | P0 |
| MCP 服务 | 4 | P1 |
| 用户信息 | 2 | P1 |
| **合计** | **16** | |
