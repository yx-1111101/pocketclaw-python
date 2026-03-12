# PocketClaw Cloud Service (Python)

基于 FastAPI + WebSocket 的设备内网穿透服务

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
# 默认端口 8764
python main.py

# 自定义端口
PORT=8764 python main.py
```

## API 接口

### 设备端接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/proxy/{device_id}` | WebSocket | 设备连接 |
| `/v1/device/heartbeat` | POST | 设备心跳 |
| `/v1/device/bind` | POST | 设备绑定 |

### 小程序端接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/device/{device_id}/status` | GET | 设备状态 |
| `/device/{device_id}` | GET | 设备信息 |
| `/device/{device_id}/bind` | DELETE | 解绑设备 |
| `/device/{device_id}/gateway/*` | POST | 网关代理 |

### 系统接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/proxy/health` | GET | 健康检查 |
| `/proxy/metrics` | GET | 系统指标 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| PORT | 8764 | 服务端口 |
| DB_FILE | data/devices.json | 数据存储文件 |
| GATEWAY_TOKEN | xxx | 默认网关 Token |

## 设备连接流程

1. 设备通过 WebSocket 连接到 `/proxy/{device_id}`
2. 设备定期发送 heartbeat 到 `/v1/device/heartbeat`
3. 小程序通过 `/device/{device_id}/gateway/*` 发送请求
4. 云端通过 WebSocket 转发请求到设备，等待响应
