# PocketClaw Cloud Service API 文档

**基础地址**: `http://43.160.215.122:8764`

---

## 目录

1. [设备端接口](#设备端接口)
2. [小程序端接口](#小程序端接口)
3. [微信登录接口](#微信登录接口)
4. [系统接口](#系统接口)

---

## 设备端接口

### 1. 设备心跳

设备联网后上报心跳。

**接口**: `POST /devices/heartbeat`

**请求体**:
```json
{
  "device_id": "ocl-xxx",
  "public_url": "https://xxx.trycloudflare.com",
  "pairing_code_hash": "sha256...",
  "pairing_code_expires": 1741594200,
  "firmware_version": "1.0.0",
  "device_secret_hash": "sha256..."
}
```

**响应**:
```json
{
  "success": true,
  "claimed": false,
  "message": "ok"
}
```

---

### 2. 设备绑定

小程序绑定设备到用户。

**接口**: `POST /devices/bind`

**请求体**:
```json
{
  "device_id": "ocl-xxx",
  "user_id": "wx-xxx",
  "pairing_code": "123456"
}
```

**响应**:
```json
{
  "success": true,
  "claimed": true,
  "message": "ok"
}
```

---

## 小程序端接口

### 3. 获取设备状态

查询设备在线状态。

**接口**: `GET /devices/{device_id}/status`

**响应**:
```json
{
  "ok": true,
  "device": {
    "device_id": "ocl-xxx",
    "status": "online",
    "last_seen": 1234567890
  }
}
```

---

### 4. 获取设备信息

获取设备完整信息。

**接口**: `GET /devices/{device_id}`

**响应**:
```json
{
  "device_id": "ocl-xxx",
  "name": "我的盒子",
  "public_url": "https://xxx.trycloudflare.com",
  "status": "online",
  "last_seen": 1234567890
}
```

---

### 5. 获取设备指标

获取设备性能指标。

**接口**: `GET /devices/{device_id}/metrics`

**响应**:
```json
{
  "cpu": 45,
  "memory": 72,
  "uptime": 3600
}
```

---

### 6. 解绑设备

解除设备与用户的绑定。

**接口**: `DELETE /devices/{device_id}/bind`

**响应**:
```json
{
  "ok": true
}
```

---

### 7. 网关代理

通过云端转发请求到设备。

**接口**: `POST /devices/{device_id}/gateway/{path}`

**请求头**:
| 头字段 | 说明 |
|--------|------|
| X-Gw-Url | 覆盖设备 URL |
| X-Gw-Token | 覆盖认证 Token |

**示例**:
```bash
curl -X POST http://43.160.215.122:8764/devices/ocl-xxx/gateway/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"hello"}'
```

---

## 微信登录接口

### 8. 微信登录

通过微信 code 获取 openid。

**接口**: `POST /api/auth/login`

**请求体**:
```json
{
  "code": "微信code"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "openid": "xxx",
    "user_id": "wx_xxx",
    "session_key": "xxx"
  }
}
```

---

### 9. 绑定手机号

微信用户绑定手机号。

**接口**: `POST /api/auth/bind-phone`

**请求体**:
```json
{
  "openid": "xxx",
  "phone": "13800138000",
  "code": "123456"
}
```

**响应**:
```json
{
  "success": true
}
```

---

### 10. 获取用户信息

获取微信用户信息。

**接口**: `GET /api/auth/user/{user_id}`

**响应**:
```json
{
  "user_id": "wx_xxx",
  "openid": "xxx",
  "phone": "13800138000",
  "nickname": "",
  "avatar": ""
}
```

---

## 系统接口

### 11. 健康检查

系统健康状态。

**接口**: `GET /health`

**响应**:
```json
{
  "ok": true,
  "status": "live",
  "ts": 1234567890
}
```

---

### 12. 系统指标

服务器性能指标。

**接口**: `GET /metrics`

**响应**:
```json
{
  "cpu": 45,
  "mem": 72,
  "ts": 1234567890
}
```

---

## 错误响应格式

```json
{
  "error": "错误描述"
}
```

| 状态码 | 说明 |
|--------|------|
| 400 | 参数错误 |
| 403 | 权限不足 |
| 404 | 资源不存在 |
| 504 | 请求超时 |
