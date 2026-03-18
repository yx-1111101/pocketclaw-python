# API 文档

**Base URL**: `http://43.160.215.122:8764`

---

## 健康检查

### GET /health
```json
{ "ok": true, "status": "live", "ts": 1234567890 }
```

### GET /metrics
```json
{ "cpu": 0, "mem": 0, "ts": 1234567890 }
```

---

## 认证 `/api/auth`

### POST /api/auth/login
微信登录，通过 wx.login() 获取的 code 换取 openid。

**请求**
```json
{ "code": "wx_code_from_login" }
```

**响应**
```json
{
  "success": true,
  "data": {
    "openid": "oLcdw3...",
    "user_id": "wx_oLcdw3...",
    "phone": "",
    "need_bind_phone": true
  }
}
```

---

### POST /api/auth/send-code
发送短信验证码（当前为 Mock 模式，不实际发送）。

**请求**
```json
{ "phone": "13800138000" }
```

**响应**
```json
{ "success": true, "message": "验证码已发送（Mock模式）" }
```

---

### POST /api/auth/verify-code
校验验证码（不消费，仅验证）。

**请求**
```json
{ "phone": "13800138000", "code": "1234" }
```

**响应**
```json
{ "success": true, "message": "验证成功" }
```

> **Mock 模式**：验证码 `1234` 万能通过，无需先调用 send-code。

---

### POST /api/auth/phone-login
手机号 + 验证码登录（验证码通过后自动查找/创建用户）。
同一手机号始终返回同一个 `user_id`（手机号作为账号归属主键）。

**请求**
```json
{ "phone": "13800138000", "code": "1234" }
```

**响应**
```json
{
  "success": true,
  "message": "登录成功",
  "data": {
    "user_id": "ph_abc123...",
    "openid": "",
    "phone": "13800138000",
    "need_bind_phone": false,
    "token": "<jwt>"
  }
}
```

---

### POST /api/auth/bind-phone
微信用户绑定手机号（需验证码）。
当手机号已存在用户时，会直接切换到该手机号用户并返回其 `user_id/token`。

**请求**
```json
{
  "openid": "oLcdw3...",
  "phone": "13800138000",
  "code": "1234"
}
```

**响应**
```json
{
  "success": true,
  "message": "绑定成功",
  "data": {
    "openid": "oLcdw3...",
    "user_id": "wx_oLcdw3...",
    "phone": "13800138000",
    "need_bind_phone": false,
    "token": "<jwt>"
  }
}
```

---

### GET /api/auth/user/{user_id}
获取用户信息。

**响应**
```json
{
  "success": true,
  "data": {
    "user_id": "wx_oLcdw3...",
    "openid": "oLcdw3...",
    "phone": "13800138000",
    "nickname": "",
    "avatar": ""
  }
}
```

---

## 设备 `/devices`

### POST /devices/heartbeat
设备心跳上报（设备端调用）。

**请求 Header**
```
x-device-id: ocl-a1b2c3d4
x-gw-token: <gateway_token>
```

**请求**
```json
{
  "device_id": "ocl-a1b2c3d4",
  "status": "online",
  "ip": "192.168.1.100"
}
```

**响应**
```json
{ "ok": true }
```

---

### POST /devices/bind
小程序绑定设备。

**请求**
```json
{
  "device_id": "ocl-a1b2c3d4",
  "pairing_code": "123456"
}
```

**响应**
```json
{
  "success": true,
  "device": {
    "device_id": "ocl-a1b2c3d4",
    "status": "online",
    "name": "My PocketClaw"
  }
}
```

---

### GET /devices/{device_id}/status
查询设备状态。

**响应**
```json
{
  "device_id": "ocl-a1b2c3d4",
  "status": "online",
  "last_seen": 1234567890
}
```

---

### GET /devices/{device_id}
获取设备详情。

---

### GET /devices/{device_id}/metrics
获取设备指标（CPU、内存等）。

---

### DELETE /devices/{device_id}/bind
解绑设备。

---

### POST /devices/{device_id}/gateway/{path}
代理转发到设备本地 Gateway（小程序无法直接访问设备，通过此接口中转）。

**示例：聊天**
```
POST /devices/ocl-a1b2c3d4/gateway/v1/chat/completions
```

**请求 Header**
```
Authorization: Bearer <auth_token>
```

**请求**：OpenAI 兼容格式
```json
{
  "model": "default",
  "messages": [{ "role": "user", "content": "你好" }],
  "stream": false
}
```

**响应**：透传设备 Gateway 的响应。

---

### GET /devices/{device_id}/models
获取设备可用模型列表（通过设备 Gateway WS `models.list`）。

**响应**
```json
{
  "success": true,
  "models": [
    {
      "id": "minimax/MiniMax-M2.5",
      "name": "MiniMax M2.5",
      "provider": "minimax",
      "contextWindow": 200000,
      "capabilities": ["text"]
    }
  ]
}
```

## 错误格式

```json
{ "success": false, "error": "错误描述" }
```

---

## 登录流程

```
方式一（微信登录）:
  wx.login() → /api/auth/login (code)
    → 返回 openid + user_id
    → 如果 need_bind_phone=true → /api/auth/send-code → /api/auth/bind-phone

方式二（手机号登录）:
  /api/auth/send-code (phone)
    → /api/auth/phone-login (phone + code)
    → 返回 user_id
```
