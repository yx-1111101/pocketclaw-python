# PocketClaw Cloud Service API 文档

**基础地址**: `http://43.160.215.122:8764`

---

## 目录

1. [小程序端接口](#小程序端接口) - 小程序调用
2. [设备端接口](#设备端接口) - 设备调用
3. [系统接口](#系统接口)

---

## 小程序端接口

### 1. 微信登录

通过微信 code 获取用户信息。

```http
POST /api/auth/login
Content-Type: application/json

{
  "code": "微信wx.login返回的code",
  "encrypted_data": "可选：getPhoneNumber返回的encryptedData",
  "iv": "可选：getPhoneNumber返回的iv"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "openid": "微信openid",
    "user_id": "wx_xxx",
    "phone": "13800138000",
    "need_bind_phone": false
  }
}
```

---

### 2. 手机号登录

手机号验证码登录（Mock），验证通过后自动查找或创建用户。

```http
POST /api/auth/phone-login
Content-Type: application/json

{
  "phone": "13800138000",
  "code": "1234"
}
```

**响应**:
```json
{
  "success": true,
  "data": {
    "user_id": "ph_xxx",
    "openid": "",
    "phone": "13800138000",
    "need_bind_phone": false
  }
}
```

---

### 3. 绑定手机号

微信用户绑定手机号。

```http
POST /api/auth/bind-phone
Content-Type: application/json

{
  "openid": "微信openid",
  "phone": "13800138000",
  "code": "1234"
}
```

**响应**:
```json
{
  "success": true
}
```

---

### 4. 获取用户信息

获取用户详情。

```http
GET /api/auth/user/{user_id}
```

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

### 4. 获取设备状态

查询设备在线状态。

```http
GET /devices/{device_id}/status
```

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

### 5. 获取设备信息

获取设备完整信息。

```http
GET /devices/{device_id}
```

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

### 6. 获取设备指标

获取设备性能指标。

```http
GET /devices/{device_id}/metrics
```

**响应**:
```json
{
  "cpu": 45,
  "memory": 72,
  "uptime": 3600
}
```

---

### 7. 绑定设备

将设备绑定到当前用户账号。

```http
POST /devices/bind
Content-Type: application/json

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

### 8. 解绑设备

解除设备与用户的绑定。

```http
DELETE /devices/{device_id}/bind
```

**响应**:
```json
{
  "ok": true
}
```

---

### 9. 网关代理

通过云端转发请求到设备。

```http
POST /devices/{device_id}/gateway/{path}
Content-Type: application/json

{
  "message": "hello"
}
```

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

## 设备端接口

### 10. 设备心跳

设备联网后上报心跳。

```http
POST /devices/heartbeat
Content-Type: application/json

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

## 系统接口

### 11. 健康检查

系统健康状态。

```http
GET /health
```

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

```http
GET /metrics
```

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
| 403 | 权限不足 / 配对码不匹配 |
| 404 | 资源不存在 |
| 504 | 请求超时 |
