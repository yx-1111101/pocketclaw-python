# PocketClaw 完整技术文档

## 系统架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   微信小程序     │     │   云端服务      │     │   设备端        │
│   (客户端)      │────▶│   (Cloud)       │◀────│   (Device)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                        │                        │
        │  HTTP / WebSocket      │  HTTP (心跳)           │
        │  - 登录               │  - 心跳上报            │
        │  - 设备绑定           │  - 配对码验证          │
        │  - 网关代理           │                        │
        │                        │                        │
        │                        │  BLE (配网)            │
        └───────────────────────┴────────────────────────┘
```

---

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 云端 API | `http://43.160.215.122:8764` | 小程序和设备共同访问 |
| 设备网关 | WebSocket `/proxy/{device_id}` | 实时消息转发 |

---

## 目录

1. [配网与绑定流程](#1-配网与绑定流程)
2. [小程序端 API](#2-小程序端-api)
3. [设备端 API](#3-设备端-api)
4. [设备 BLE 接口](#4-设备-ble-接口)
5. [云端 API](#5-云端-api)
6. [错误码](#6-错误码)

---

## 1. 配网与绑定流程

### 1.1 完整流程图

```
┌─────────┐  BLE      ┌─────────┐  HTTP    ┌─────────┐
│  小程序  │─────────▶│  设备   │─────────▶│  云端   │
└─────────┘           └─────────┘          └─────────┘
     │                                          │
     │  1. 扫描发现设备                          │
     │  2. 连接 BLE                            │
     │  3. 读取 Device Info                    │
     │  (device_id, pairing_code)              │
     │                                          │
     │  4. 发送 WiFi 凭证 ──────────────────────▶
     │     (WiFi SSID + Password)               │
     │                                          │
     │                    5. 设备联网            │
     │                    6. 心跳上报 ──────────▶
     │                       (pairing_code_hash) │
     │                                          │
     │  7. 轮询设备状态                          │
     │     GET /devices/{id}/status             │
     │                                          │
     │  8. 绑定设备 ────────────────────────────▶
     │     POST /devices/bind                   │
     │     (pairing_code 明文)                  │
     │                                          │
     │  9. 网关代理 ◀───────────────────────────
     │     POST /devices/{id}/gateway/*         │
```

### 1.2 配对码机制

- **生成**: 设备启动时生成 6 位数字配对码
- **有效期**: 默认 30 分钟（可配置）
- **用途**: 验证设备归属，防止恶意绑定
- **验证**: 
  - 设备心跳时上传 `pairing_code_hash` (SHA256)
  - 小程序绑定时上传明文 `pairing_code`
  - 云端比对 hash 是否一致

---

## 2. 小程序端 API

### 2.1 认证接口

#### 微信登录

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

#### 绑定手机号

```http
POST /api/auth/bind-phone
Content-Type: application/json

{
  "openid": "微信openid",
  "phone": "13800138000"
}
```

#### 获取用户信息

```http
GET /api/auth/user/{user_id}
```

---

### 2.2 设备接口

#### 获取设备列表

```http
GET /devices
```

#### 获取设备状态

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

#### 获取设备信息

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

#### 获取设备指标

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

#### 绑定设备

```http
POST /devices/bind
Content-Type: application/json

{
  "device_id": "ocl-xxx",
  "user_id": "wx-xxx",
  "pairing_code": "123456"
}
```

#### 解绑设备

```http
DELETE /devices/{device_id}/bind
```

---

### 2.3 网关代理

小程序通过云端转发请求到设备：

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

---

## 3. 设备端 API

设备主动上报心跳到云端：

### 3.1 设备心跳

```http
POST /devices/heartbeat
Content-Type: application/json

{
  "device_id": "ocl-xxx",
  "public_url": "https://xxx.trycloudflare.com",
  "pairing_code_hash": "sha256后的配对码",
  "pairing_code_expires": 1741594200,
  "firmware_version": "1.0.0",
  "device_secret_hash": "sha256后的设备密钥"
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

## 4. 设备 BLE 接口

设备 BLE GATT 服务结构：

| Service UUID | 广播名 |
|--------------|--------|
| `0000FFF0-0000-1000-8000-00805F9B34FB` | `BoxSetup-{设备ID后6位}` |

### 4.1 特征值

| 名称 | UUID | 属性 | 说明 |
|------|------|------|------|
| Device Info | FFF2 | Read | 设备身份信息 |
| WiFi Credential | FFF1 | Write | WiFi 凭据 |
| Prov Status | FFF3 | Read/Notify | 配网状态 |

### 4.2 Device Info (FFF2)

设备返回 JSON：
```json
{
  "device_id": "box-a1b2c3d4",
  "pairing_code": "839274",
  "pairing_code_expires": 1741594200,
  "network_ready": false,
  "version": "1.0.0"
}
```

### 4.3 WiFi Credential (FFF1)

小程序发送 JSON：
```json
{
  "ssid": "MyWiFi",
  "password": "wifi密码",
  "connect": true
}
```

### 4.4 Prov Status (FFF3)

设备通知配网进度：
```json
{
  "status": "connecting",
  "ip": "192.168.1.100",
  "error": null
}
```

**状态值**:
- `idle`: 等待配网
- `connecting`: 连接中
- `connected`: 已连接
- `failed`: 失败

---

## 5. 云端 API

### 5.1 健康检查

```http
GET /health
```

### 5.2 系统指标

```http
GET /metrics
```

---

## 6. 错误码

| 错误码 | 说明 |
|--------|------|
| 400 | 参数错误 |
| 403 | 权限不足 / 配对码不匹配 |
| 404 | 资源不存在 |
| 504 | 请求超时 |

**错误响应格式**:
```json
{
  "error": "错误描述"
}
```

---

## 数据表结构

### users 表

```sql
CREATE TABLE users (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  openid VARCHAR(64) UNIQUE,
  phone VARCHAR(20),
  nickname VARCHAR(50),
  avatar VARCHAR(255),
  status INT DEFAULT 1,
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### devices 表

```sql
CREATE TABLE devices (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  device_id VARCHAR(64) UNIQUE,
  name VARCHAR(64),
  public_url VARCHAR(255),
  pairing_code_hash VARCHAR(64),
  pairing_code_expires DATETIME,
  device_secret_hash VARCHAR(64),
  status VARCHAR(20) DEFAULT 'offline',
  last_seen BIGINT,
  firmware_version VARCHAR(20),
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### device_bindings 表

```sql
CREATE TABLE device_bindings (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT,
  device_id BIGINT,
  role VARCHAR(20) DEFAULT 'owner',
  create_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
