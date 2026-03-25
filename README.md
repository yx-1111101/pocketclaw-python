# PocketClaw Python Backend

基于 **FastAPI + WebSocket** 的设备内网穿透云服务，支持小程序与设备之间的消息代理。

## 功能

- 微信 + 手机号双登录
- 短信验证码（当前 Mock 模式，验证码 `1234` 万能通过）
- 设备注册 & 心跳管理
- 小程序 → 云端 → 设备的 API 代理（聊天、指令等）
- MySQL 持久化存储（未配置时自动降级到内存模式）

## 快速启动

```bash
# 创建并激活虚拟环境（推荐，避免 externally-managed-environment）
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入实际值（见下方说明）

# 初始化数据库
mysql -h <host> -u <user> -p < sql/create_tables.sql

# 启动两个服务（主服务 + LLM 代理）
./start.sh

# 或单独启动主服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8764
```

## 配置 .env

复制模板后编辑：

```bash
cp .env.example .env
```

| 变量 | 必填 | 说明 |
|------|------|------|
| `PORT` | 否 | 主服务监听端口，默认 `8764` |
| `LLM_PROXY_PORT` | 否 | LLM 代理服务端口，默认 `8765` |
| `JWT_SECRET` | **是** | 用户 Token 签名密钥，需保密且稳定（更换会使所有用户登录失效） |
| `MYSQL_HOST` | 否 | MySQL 主机，默认 `localhost` |
| `MYSQL_PORT` | 否 | MySQL 端口，默认 `3306` |
| `MYSQL_USER` | 否 | MySQL 用户名，默认 `root` |
| `MYSQL_PASSWORD` | 否 | MySQL 密码，默认空 |
| `MYSQL_DB` | 否 | MySQL 数据库名，默认 `openfriday` |
| `REDIS_HOST` | 否 | Redis 主机，默认 `localhost` |
| `REDIS_PORT` | 否 | Redis 端口，默认 `6379` |
| `REDIS_DB` | 否 | Redis 数据库编号，默认 `0` |
| `WECHAT_APP_ID` | 否 | 微信小程序 AppID |
| `WECHAT_APP_SECRET` | 否 | 微信小程序 AppSecret |

> **设备 Token**：无需手动配置。设备在心跳时自动上报 `device_secret_hash`，云端从数据库按设备动态读取。

## 目录结构

```
pocketclaw-python/
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── core/
│   │   ├── websocket.py # 设备 WebSocket 管理
│   │   ├── db.py        # MySQL 数据库客户端
│   │   ├── security.py  # 安全工具（JWT）
│   │   └── sms.py       # 短信验证码（Mock 模式）
│   └── models/
│       └── schemas.py   # Pydantic 数据模型
├── api/
│   ├── wechat.py        # 认证路由 /api/auth/*
│   ├── device.py        # 设备路由 /devices/*
│   └── proxy.py         # 代理路由
├── llm_proxy/           # LLM 代理子服务（默认 8765 端口）
├── sql/
│   └── create_tables.sql  # 数据库建表脚本
├── requirements.txt
├── API.md               # 接口文档
└── README.md
```

## API 概览

| 接口 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /api/auth/login` | 微信登录 |
| `POST /api/auth/send-code` | 发送验证码 |
| `POST /api/auth/verify-code` | 校验验证码 |
| `POST /api/auth/phone-login` | 手机号登录 |
| `POST /api/auth/bind-phone` | 绑定手机号 |
| `GET /api/auth/user/{user_id}` | 获取用户信息 |
| `POST /devices/heartbeat` | 设备心跳 |
| `POST /devices/bind` | 绑定设备 |
| `GET /devices/{id}/status` | 设备状态 |
| `POST /devices/{id}/gateway/{path}` | 代理转发到设备 |

完整文档见 [API.md](./API.md)。

## 登录流程

```
微信登录:
  wx.login() → POST /api/auth/login → openid + user_id
  如需绑定手机: POST /api/auth/send-code → POST /api/auth/bind-phone

手机号登录:
  POST /api/auth/send-code → POST /api/auth/phone-login → user_id
```

## 部署

服务运行于 `43.160.215.122:8764`，直接 `python3 -m app.main` 启动即可。

建议配合 `pm2` 或 `systemd` 管理进程：

```bash
pm2 start "python3 -m app.main" --name pocketclaw --cwd /path/to/pocketclaw-python
```
