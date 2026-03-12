# PocketClaw Cloud Service

基于 FastAPI + WebSocket + Supabase 的设备内网穿透服务

## 项目结构

```
pocketclaw-python/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   └── core/
│       ├── __init__.py
│       ├── supabase.py      # Supabase 客户端
│       ├── websocket.py     # WebSocket 管理
│       └── security.py     # 安全工具
│   └── models/
│       ├── __init__.py
│       └── schemas.py       # Pydantic 模型
├── api/
│   ├── __init__.py
│   ├── device.py           # 设备 API
│   ├── wechat.py          # 微信登录 API
│   └── proxy.py           # 网关代理 API
├── public/                     # 静态文件
├── database.sql              # 数据库表结构
├── requirements.txt
└── README.md
```

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
# 开发模式
python -m app.main

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8764
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| PORT | 8764 | 服务端口 |
| SUPABASE_URL | - | Supabase 项目 URL |
| SUPABASE_KEY | - | Supabase Service Role Key |
| WECHAT_APP_ID | - | 微信小程序 AppID |
| WECHAT_APP_SECRET | - | 微信小程序 AppSecret |
| GATEWAY_TOKEN | - | 网关 Token |
