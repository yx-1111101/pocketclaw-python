# PocketClaw - 云端后端

PocketClaw 云端中继服务器，为小程序与设备之间提供通信桥梁。

## 技术栈

- Python 3
- FastAPI + uvicorn + websockets
- aiomysql + redis
- httpx + pydantic + python-dotenv + pycryptodome

## 关键目录

- `app/main.py` — 主应用入口（推荐用 `uvicorn app.main:app` 启动）
- `api/` — 各域路由
- `app/core/` — 核心逻辑
- `llm_proxy/` — LLM 代理子服务
- `sql/create_tables.sql` — 数据库建表
- `docs/` + `API.md` — 接口文档

## 核心功能

- 用户登录、设备注册与管理
- 小程序到设备的 RPC/WebSocket 代理
- 技能/MCP 管理
- 计费
- LLM 请求代理（HMAC 签名）

## 通信方式

- 小程序 → HTTP/WebSocket 请求
- 设备 → WebSocket 长连接（`/proxy/{device_id}`）、HTTP 心跳
- 设备 LLM 代理 → HTTP（`/llm/chat/completions`），HMAC 签名

## 编码约定

- 环境变量通过 `.env` 管理
- CORS `allow_origins=["*"]`
