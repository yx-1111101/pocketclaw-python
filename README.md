# PocketClaw Python Backend

基于 **FastAPI + WebSocket** 的设备内网穿透云服务，支持小程序与设备之间的消息代理。

## 功能

- 微信 + 手机号双登录
- 短信验证码（当前 Mock 模式，验证码 `1234` 万能通过）
- 设备注册 & 心跳管理
- 小程序 → 云端 → 设备的 API 代理（聊天、指令等）
- 可选 Supabase 持久化（未配置时仍可运行）

## 快速启动

```bash
# 安装依赖
pip3 install -r requirements.txt

# 启动服务（默认 8764 端口）
python3 -m app.main
```

环境变量（可选，未配置时使用内置默认值）：

| 变量 | 说明 |
|------|------|
| `PORT` | 监听端口，默认 `8764` |
| `WECHAT_APP_ID` | 微信小程序 AppID |
| `WECHAT_APP_SECRET` | 微信小程序 AppSecret |
| `GATEWAY_TOKEN` | 设备 Gateway 默认 Token |
| `SUPABASE_URL` | Supabase 项目 URL（可选） |
| `SUPABASE_KEY` | Supabase anon key（可选） |

## 目录结构

```
pocketclaw-python/
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── config.py        # 配置（环境变量 + 默认值）
│   ├── core/
│   │   ├── websocket.py # 设备 WebSocket 管理
│   │   ├── supabase.py  # 数据库客户端
│   │   ├── security.py  # 安全工具
│   │   └── sms.py       # 短信验证码（Mock 模式）
│   └── models/
│       └── schemas.py   # Pydantic 数据模型
├── api/
│   ├── wechat.py        # 认证路由 /api/auth/*
│   ├── device.py        # 设备路由 /devices/*
│   └── proxy.py         # 代理路由
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
