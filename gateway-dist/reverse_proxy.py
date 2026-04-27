#!/usr/bin/env python3
"""
设备端反向代理客户端 (pocketclaw-device)

通过 WebSocket 长连接主动连接到云端 pocketclaw-python 的 /proxy/{device_id}，
接收云端转发的请求，路由到本地 HTTP 服务（file-server、setup-server、OpenClaw Gateway），
并将响应回传给云端。

用法：
    python3 reverse_proxy.py
    # 或者作为 systemd service 运行（见 systemd/ 目录）
"""

import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import httpx
import websockets
from websockets.exceptions import ConnectionClosed
from websockets.protocol import State

log = logging.getLogger("pocketclaw-device")

# 本地服务地址（默认值，可被 config.json 覆盖）
DEFAULT_FILE_SERVER = "http://127.0.0.1:18790"
DEFAULT_SETUP_SERVER = "http://127.0.0.1:8088"
DEFAULT_GATEWAY_WS = "ws://127.0.0.1:18789"
DEFAULT_LLM_API_SERVER = "http://127.0.0.1:20002"

# 运行时实际使用的地址（由 start() 从 config.json 初始化）
FILE_SERVER = DEFAULT_FILE_SERVER
SETUP_SERVER = DEFAULT_SETUP_SERVER
GATEWAY_WS = DEFAULT_GATEWAY_WS
LLM_API_SERVER = DEFAULT_LLM_API_SERVER

# 默认超时
HTTP_TIMEOUT = 120.0

# 流式对话 function 名（默认值，可被 config.json 覆盖）
DEFAULT_STREAM_FUNCTIONS = ("v1/chat/completions", "chat/completions", "chat.send")
STREAM_FUNCTIONS: tuple[str, ...] = DEFAULT_STREAM_FUNCTIONS


def _extract_text_from_content(content) -> str:
    """尽量从 Gateway/OpenAI 风格 content 中提取文本。"""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
                continue
            if not isinstance(p, dict):
                continue
            # 常见：{"type":"text","text":"..."}
            if isinstance(p.get("text"), str):
                parts.append(p["text"])
                continue
            # 兼容：{"type":"thinking","thinking":"..."}
            if isinstance(p.get("thinking"), str):
                parts.append(p["thinking"])
        return "".join(parts)
    if isinstance(content, dict):
        # 兼容：{"value":"..."}
        v = content.get("value")
        return v if isinstance(v, str) else ""
    return ""


def _extract_delta(payload: dict) -> str:
    """
    从 Gateway agent/chat 事件 payload 中提取增量文本。
    兼容多种结构：
    - payload.data.delta
    - payload.delta
    - OpenAI chunk: payload.data.choices[0].delta.content
    - message/content 结构：payload.message.content 或 payload.content
    """
    if not isinstance(payload, dict):
        return ""
    d = payload.get("data")
    if isinstance(d, dict):
        delta = d.get("delta")
        if isinstance(delta, str) and delta:
            return delta
        # OpenAI stream chunk
        choices = d.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            delta_obj = first.get("delta") if isinstance(first, dict) else {}
            if isinstance(delta_obj, dict):
                c = delta_obj.get("content")
                if isinstance(c, str) and c:
                    return c
    delta2 = payload.get("delta")
    if isinstance(delta2, str) and delta2:
        return delta2
    # message/content fallback（非严格 delta，但至少别丢文本）
    msg = payload.get("message")
    if isinstance(msg, dict):
        c = msg.get("content")
        text = _extract_text_from_content(c)
        if text:
            return text
    text = _extract_text_from_content(payload.get("content"))
    return text

def _extract_chat_event_text(message) -> str:
    """从 chat 事件的 message 字段提取 assistant 回复文本。"""
    if not isinstance(message, dict):
        return ""
    if message.get("role") not in ("assistant", None):
        return ""
    content = message.get("content")
    text = _extract_text_from_content(content)
    if text:
        return text
    text_field = message.get("text")
    if isinstance(text_field, str) and text_field.strip():
        return text_field
    return ""


# ── 文件预处理：解析消息中的文件引用，在设备端本地读取并注入上下文 ──────────

_FILE_REF_RE = re.compile(r'\[用户上传了(图片|文件) "([^"]+)"\]')

_IMAGE_EXTS = frozenset({"jpg", "jpeg", "png", "gif", "webp", "bmp"})
_TEXT_EXTS = frozenset({
    "txt", "md", "json", "csv", "py", "js", "ts", "jsx", "tsx",
    "log", "yaml", "yml", "toml", "xml", "html", "css", "sh",
    "sql", "ini", "cfg", "conf", "env", "go", "rs", "java",
    "c", "cpp", "h", "hpp", "rb", "php", "swift", "kt",
})
_TEXT_SIZE_LIMIT = 200 * 1024  # 200KB，超过不内联
_TOTAL_ATTACHMENT_LIMIT = 10 * 1024 * 1024  # 10MB 单条消息上限


def _resolve_workspace(session_key: str) -> str:
    """从 sessionKey 和 openclaw.json 解析 agent 的 workspace 路径。"""
    default_ws = str(Path.home() / ".openclaw" / "workspace")
    openclaw_json = Path.home() / ".openclaw" / "openclaw.json"
    try:
        with open(openclaw_json) as f:
            cfg = json.load(f)
        agents = cfg.get("agents", {})
        # agents.defaults.workspace 是默认 workspace
        defaults = agents.get("defaults", {})
        ws = defaults.get("workspace", "")
        if ws:
            default_ws = ws
    except Exception:
        pass
    return default_ws


def _ext_of(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _preprocess_file_references(message: str, session_key: str) -> tuple[str, list | None]:
    """
    解析消息中的 [用户上传了...] 引用，从本地 workspace 读取文件内容。

    - 图片 → base64 编码加入 attachments
    - 纯文本 → <file_content> 标记包裹后拼入 message
    - 其他 → 保留原始引用不处理

    返回 (processed_message, attachments_or_none)。
    尽力而为：任何文件读取失败都保留原始引用，不影响消息发送。
    """
    matches = list(_FILE_REF_RE.finditer(message))
    if not matches:
        return message, None

    workspace_dir = _resolve_workspace(session_key)
    attachments: list[dict] = []
    text_appendix: list[str] = []
    total_att_size = 0

    for m in matches:
        ref_type, file_ref = m.group(1), m.group(2)
        file_path = os.path.join(workspace_dir, file_ref)

        if not os.path.isfile(file_path):
            log.warning("[preprocess] 文件不存在: %s", file_path)
            continue

        ext = _ext_of(file_ref)
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            continue

        # 图片：base64 编码
        if ext in _IMAGE_EXTS:
            if total_att_size + file_size > _TOTAL_ATTACHMENT_LIMIT:
                log.warning("[preprocess] 跳过图片（超出总大小限制）: %s", file_ref)
                continue
            try:
                with open(file_path, "rb") as f:
                    raw = f.read()
                b64 = base64.b64encode(raw).decode("ascii")
                mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
                attachments.append({"type": "image", "mimeType": mime, "content": b64})
                total_att_size += file_size
                log.info("[preprocess] 图片已编码: %s (%s)", file_ref, _human_size(file_size))
            except Exception as e:
                log.warning("[preprocess] 图片读取失败: %s %s", file_ref, e)

        # 纯文本：读取内容包裹标记
        elif ext in _TEXT_EXTS:
            if file_size > _TEXT_SIZE_LIMIT:
                log.info("[preprocess] 文本文件过大，跳过内联: %s (%s)", file_ref, _human_size(file_size))
                continue
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                text_appendix.append(
                    f'\n<file_content path="{file_ref}" size="{_human_size(file_size)}">\n'
                    f'{content}\n'
                    f'</file_content>'
                )
                log.info("[preprocess] 文本已内联: %s (%s)", file_ref, _human_size(file_size))
            except Exception as e:
                log.warning("[preprocess] 文本读取失败: %s %s", file_ref, e)

        # 其他二进制格式：不处理，保留引用
        else:
            log.debug("[preprocess] 跳过不支持的格式: %s (ext=%s)", file_ref, ext)

    # 拼接文本附录
    processed_message = message
    if text_appendix:
        processed_message = message + "".join(text_appendix)

    return processed_message, attachments if attachments else None


# 配置文件路径（与本脚本同目录）
CONFIG_PATH = Path(__file__).parent / "config.json"
ROUTES_PATH = Path(__file__).parent / "routes.json"
GATEWAY_IDENTITY_PATH = Path(__file__).parent / "gateway_identity.json"

# HTTP 路由表：由 _init_routes() 在 start() 中根据 config.json 初始化
ROUTE_TABLE: list[tuple] = []

# HTTP 白名单前缀列表：由 _init_routes() 从 routes.json 加载
HTTP_WHITELIST: list[str] = []


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"读取 config.json 失败: {e}")
        return {}


def _load_gateway_identity() -> dict:
    try:
        if GATEWAY_IDENTITY_PATH.exists():
            return json.loads(GATEWAY_IDENTITY_PATH.read_text())
    except Exception as e:
        log.warning(f"读取 gateway_identity.json 失败: {e}")
    return {}


def _save_gateway_identity(data: dict):
    try:
        GATEWAY_IDENTITY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        log.warning(f"写入 gateway_identity.json 失败: {e}")


def _load_routes_config() -> dict:
    try:
        with open(ROUTES_PATH) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"读取 routes.json 失败: {e}，HTTP 白名单为空（将拒绝所有 HTTP 代理请求）")
        return {}


def _init_routes(config: dict):
    """根据 config.json 初始化模块级路由变量，在 start() 中调用一次。"""
    global FILE_SERVER, SETUP_SERVER, GATEWAY_WS, LLM_API_SERVER, ROUTE_TABLE, STREAM_FUNCTIONS, HTTP_WHITELIST

    FILE_SERVER = config.get("file_server_url", DEFAULT_FILE_SERVER).rstrip("/")
    SETUP_SERVER = config.get("setup_server_url", DEFAULT_SETUP_SERVER).rstrip("/")
    GATEWAY_WS = config.get("gateway_ws_url", DEFAULT_GATEWAY_WS).rstrip("/")
    LLM_API_SERVER = config.get("llm_api_server_url", "http://127.0.0.1:20002").rstrip("/")

    ROUTE_TABLE = [
        ("setup/", SETUP_SERVER),
        ("files/", FILE_SERVER),
        ("llm/", LLM_API_SERVER, True),  # preserve prefix, like nginx proxy_pass with full path
    ]

    sf = config.get("stream_functions")
    if isinstance(sf, list) and sf:
        STREAM_FUNCTIONS = tuple(sf)
    else:
        STREAM_FUNCTIONS = DEFAULT_STREAM_FUNCTIONS

    routes_cfg = _load_routes_config()
    wl = routes_cfg.get("http_whitelist")
    HTTP_WHITELIST = list(wl) if isinstance(wl, list) else []

    log.info(
        f"路由初始化完成: file_server={FILE_SERVER}  "
        f"setup_server={SETUP_SERVER}  gateway_ws={GATEWAY_WS}  "
        f"stream_functions={STREAM_FUNCTIONS}  "
        f"http_whitelist={len(HTTP_WHITELIST)} 条规则"
    )


def _load_device_id(config: dict) -> str:
    """优先从环境变量读取 device_id，其次从 gateway_identity.json，最后从 openclaw 共享模块读取。"""
    env_id = os.environ.get("OPENCLAW_DEVICE_ID", "").strip()
    if env_id:
        return env_id

    gw_id = _load_gateway_identity().get("device_id", "").strip()
    if gw_id:
        return gw_id

    try:
        import openclaw_device_state as ds
        return ds.load_identity().get("device_id", "")
    except Exception:
        pass
    return ""


def _is_http_whitelisted(function: str) -> bool:
    """检查 HTTP 路径是否在白名单中（前缀匹配）。"""
    if not HTTP_WHITELIST:
        return False
    return any(function == prefix or function.startswith(prefix + "/")
               for prefix in HTTP_WHITELIST)


def _resolve_route(function: str) -> tuple[str, str]:
    """
    根据 function 字段解析出 (base_url, path)。
    例如：
      "setup/api/config"    → (SETUP_SERVER, "/api/config")
      "files/api/files"     → (FILE_SERVER,  "/api/files")
      "llm/api/config"      → (LLM_API_SERVER, "/llm/api/config")  # prefix preserved
      "v1/chat/completions" → (FILE_SERVER,  "/v1/chat/completions")
    """
    for entry in ROUTE_TABLE:
        prefix, base_url = entry[0], entry[1]
        keep_prefix = len(entry) > 2 and entry[2]
        if function.startswith(prefix):
            path = "/" + (function if keep_prefix else function[len(prefix):])
            return base_url, path

    return FILE_SERVER, "/" + function


async def _handle_upload(
    client: httpx.AsyncClient,
    request_id: str,
    function: str,
    params: dict,
) -> dict:
    """处理文件上传请求。params 中包含 _file_b64 (base64 编码) 和 _filename。"""
    base_url, path = _resolve_route(function)
    url = base_url + path
    query = params.pop("_query", None)
    headers = params.pop("_headers", {})
    file_b64 = params.pop("_file_b64", "")
    filename = params.pop("_filename", "upload.bin")
    content_type = params.pop("_content_type", "application/octet-stream")

    try:
        file_bytes = base64.b64decode(file_b64)
        files = {"file": (filename, file_bytes, content_type)}
        resp = await client.post(url, files=files, params=query, headers=headers, timeout=HTTP_TIMEOUT)

        ct = resp.headers.get("content-type", "")
        if "application/json" in ct:
            return {"request_id": request_id, "data": resp.json()}
        return {"request_id": request_id, "data": {"_raw": resp.text, "_status": resp.status_code}}
    except Exception as e:
        log.error(f"上传失败: {url}: {e}")
        return {"request_id": request_id, "data": {"error": str(e)}}


async def _handle_download(
    client: httpx.AsyncClient,
    request_id: str,
    function: str,
    params: dict,
) -> dict:
    """处理文件下载请求。返回 base64 编码的文件内容。"""
    base_url, path = _resolve_route(function)
    url = base_url + path
    query = params.pop("_query", None)
    headers = params.pop("_headers", {})

    try:
        resp = await client.get(url, params=query, headers=headers, timeout=HTTP_TIMEOUT)
        ct = resp.headers.get("content-type", "")

        if "application/json" in ct:
            return {"request_id": request_id, "data": resp.json()}

        file_b64 = base64.b64encode(resp.content).decode("ascii")
        return {
            "request_id": request_id,
            "data": {
                "_file_b64": file_b64,
                "_content_type": ct,
                "_status": resp.status_code,
            },
        }
    except Exception as e:
        log.error(f"下载失败: {url}: {e}")
        return {"request_id": request_id, "data": {"error": str(e)}}


async def _handle_request(
    client: httpx.AsyncClient,
    request_id: str,
    function: str,
    params: dict,
) -> dict:
    """处理单个来自云端的请求，路由到本地服务并返回结果。"""
    if params.get("_upload"):
        params.pop("_upload")
        return await _handle_upload(client, request_id, function, params)
    if params.get("_download"):
        params.pop("_download")
        return await _handle_download(client, request_id, function, params)

    base_url, path = _resolve_route(function)
    method = params.pop("_method", "POST").upper()
    headers = params.pop("_headers", {})

    url = base_url + path
    query = params.pop("_query", None)

    try:
        # Use generic request() method to support all HTTP methods (GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD, etc.)
        if method in ("GET", "DELETE", "HEAD", "OPTIONS"):
            # Methods that typically don't send a body
            resp = await client.request(method, url, params=query, headers=headers, timeout=HTTP_TIMEOUT)
        else:
            # Methods that can send a body (POST, PUT, PATCH, etc.)
            resp = await client.request(method, url, json=params, params=query, headers=headers, timeout=HTTP_TIMEOUT)

        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            data = resp.json()
        else:
            ct = (content_type or "").lower()
            if ct.startswith("text/"):
                data = {"_raw": resp.text, "_status": resp.status_code}
            else:
                file_b64 = base64.b64encode(resp.content).decode("ascii")
                data = {
                    "_file_b64": file_b64,
                    "_content_type": content_type or "application/octet-stream",
                    "_status": resp.status_code,
                }

        return {"request_id": request_id, "data": data}

    except httpx.TimeoutException:
        log.warning(f"请求超时: {method} {url}")
        return {"request_id": request_id, "data": {"error": "timeout", "detail": f"{method} {url} 超时"}}
    except Exception as e:
        log.error(f"请求失败: {method} {url}: {e}")
        return {"request_id": request_id, "data": {"error": str(e)}}


class GatewayBridge:
    """
    维护一个到 OpenClaw Gateway 的 WebSocket 长连接。
    用于处理流式对话请求：发送消息后持续收集事件，透传给云端。
    """

    def __init__(self, gateway_token: str):
        self.gateway_token = gateway_token
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._authenticated = False
        # 流式监听器：必须支持“同一个 sessionKey 并发多请求/多客户端”
        # 以前用 dict[session]->queue 会被并发覆盖，导致丢事件/流式超时
        self._stream_listeners: dict[str, "GatewayBridge._StreamListener"] = {}
        self._stream_listener_seq = 0
        self._req_id_counter = 10
        self._pending_responses: dict[str, asyncio.Future] = {}
        self._reader_task: Optional[asyncio.Task] = None

    @staticmethod
    def _ws_is_open(ws) -> bool:
        """兼容 websockets 旧版(protocol.open) 与 16.x (connection.state)。"""
        if ws is None:
            return False
        # websockets <= 15
        old_open = getattr(ws, "open", None)
        if isinstance(old_open, bool):
            return old_open
        # websockets >= 16
        state = getattr(ws, "state", None)
        if state is not None:
            return state == State.OPEN
        return False

    @dataclass
    class _StreamListener:
        id: str
        session_key: str
        queue: asyncio.Queue
        run_id: str = ""
        created_at: float = 0.0

        @property
        def legacy_key(self) -> str:
            # 兼容旧逻辑：用最后一段做模糊匹配（例如 "agent:main:main" -> "main"）
            sk = self.session_key or ""
            return sk.split(":")[-1] if ":" in sk else sk

    async def connect(self):
        if self._ws_is_open(self._ws):
            return
        self._authenticated = False
        try:
            self._ws = await websockets.connect(
                GATEWAY_WS,
                origin="http://localhost:5173",
                ping_interval=30,
                ping_timeout=10,
                max_size=20 * 1024 * 1024,
            )
            self._reader_task = asyncio.create_task(self._reader_loop())
            log.info("[GatewayBridge] 已连接 Gateway WS")
        except Exception as e:
            log.warning(f"[GatewayBridge] 连接 Gateway 失败: {e}")
            self._ws = None

    async def _reader_loop(self):
        try:
            async for raw in self._ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "event" and data.get("event") == "connect.challenge":
                    await self._ws.send(json.dumps({
                        "type": "req", "id": "1", "method": "connect",
                        "params": {
                            "minProtocol": 3, "maxProtocol": 3,
                            "role": "operator",
                            "scopes": ["operator.read", "operator.write", "operator.admin"],
                            "auth": {"token": self.gateway_token},
                            "client": {"id": "openclaw-tui", "version": "1.0.0",
                                    "platform": "linux", "mode": "cli"},
                            "caps": ["tool-events"],
                            "commands": [],
                            "permissions": {},
                        },
                    }))
                    continue

                if data.get("type") == "res" and data.get("id") == "1":
                    self._authenticated = data.get("ok", False)
                    if self._authenticated:
                        log.info("[GatewayBridge] Gateway 认证成功")
                    else:
                        log.error("[GatewayBridge] Gateway 认证失败")
                    continue

                if data.get("type") == "res":
                    rid = data.get("id", "")
                    if rid in self._pending_responses:
                        self._pending_responses[rid].set_result(data)
                        del self._pending_responses[rid]
                    continue

                # agent 事件（思考/文本/工具进度/生命周期）和 chat 事件（工具调用最终结果）
                # 都需要路由到对应 session 的监听队列
                event_name = data.get("event", "")
                if data.get("type") == "event" and event_name in ("agent", "chat"):
                    payload = data.get("payload", {}) or {}
                    session_key = payload.get("sessionKey", "") or ""
                    run_id = payload.get("runId") or payload.get("run_id") or ""
                    # 路由到匹配的监听器；优先精确匹配 sessionKey，其次兼容 legacy_key 的包含匹配
                    for listener in list(self._stream_listeners.values()):
                        try:
                            if not listener.session_key:
                                continue
                            if session_key == listener.session_key or (listener.legacy_key and listener.legacy_key in session_key):
                                # 一旦首次看到 runId，绑定到该 listener，后续只收同一 runId 的事件，避免同 session 并发串流
                                if run_id and not listener.run_id:
                                    listener.run_id = str(run_id)
                                if listener.run_id and run_id and str(run_id) != listener.run_id:
                                    continue
                                await listener.queue.put(data)
                        except Exception:
                            continue

        except ConnectionClosed:
            log.warning("[GatewayBridge] Gateway WS 连接断开")
        except Exception as e:
            log.error(f"[GatewayBridge] reader 异常: {e}")
        finally:
            self._authenticated = False
            self._ws = None

    async def ensure_connected(self):
        if not self._ws_is_open(self._ws):
            await self.connect()
            for _ in range(30):
                if self._authenticated:
                    return True
                await asyncio.sleep(0.2)
            return False
        return self._authenticated

    async def rpc(self, method: str, params: dict, timeout: float = 30.0) -> dict:
        """
        向 Gateway 发一次 RPC 请求，等待 res 后返回结果。
        用于 skills.status / skills.update / skills.install 等，不走 HTTP。
        """
        if not await self.ensure_connected():
            return {"error": "Gateway not connected"}
        self._req_id_counter += 1
        rid = str(self._req_id_counter)
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[rid] = future
        try:
            await self._ws.send(json.dumps({
                "type": "req", "id": rid, "method": method, "params": params,
            }))
            res = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"error": "Gateway RPC timeout", "method": method}
        finally:
            self._pending_responses.pop(rid, None)

        log.debug(f"[GW RPC] res={str(res)[:300]}")
        if res.get("ok"):
            # Gateway 响应格式是 {type:"res", id, ok, payload}，不是 result
            return res.get("payload", res.get("result", {}))
        return {"error": res.get("error", "unknown"), "method": method}

    async def send_chat_and_stream(
        self, session_key: str, message: str, cloud_ws, request_id: str,
        attachments: list | None = None,
    ):
        """向 Gateway 发送 chat.send，然后持续收集事件并透传给云端 WebSocket。"""
        # 预处理：解析消息中的文件引用，在本地读取并注入上下文
        processed_msg, local_attachments = _preprocess_file_references(message, session_key)
        # 合并：云端传来的 attachments + 本地提取的 attachments
        merged_attachments = (attachments or []) + (local_attachments or []) or None

        log.info(
            "[CHAT >>] session=%s message=%s attachments=%d (local=%d)",
            session_key, (processed_msg or "")[:200],
            len(merged_attachments) if merged_attachments else 0,
            len(local_attachments) if local_attachments else 0,
        )
        if not await self.ensure_connected():
            await cloud_ws.send(json.dumps({
                "request_id": request_id,
                "data": {"error": "Gateway not connected"},
            }))
            return

        self._req_id_counter += 1
        rid = str(self._req_id_counter)

        event_queue: asyncio.Queue = asyncio.Queue()
        self._stream_listener_seq += 1
        listener_id = f"l{int(time.time()*1000)}-{self._stream_listener_seq}"
        listener = self._StreamListener(
            id=listener_id,
            session_key=session_key,
            queue=event_queue,
            created_at=time.time(),
        )
        self._stream_listeners[listener_id] = listener

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[rid] = future

        chat_params = {
            "sessionKey": session_key,
            "message": processed_msg,
            "idempotencyKey": f"rp-{int(time.time() * 1000)}",
        }
        if merged_attachments:
            chat_params["attachments"] = merged_attachments
        await self._ws.send(json.dumps({
            "type": "req", "id": rid, "method": "chat.send",
            "params": chat_params,
        }))

        try:
            res = await asyncio.wait_for(future, timeout=10)
            run_id = res.get("payload", {}).get("runId", "") if isinstance(res.get("payload"), dict) else ""
            log.info(
                "[CHAT] chat.send ack ok=%s runId=%s keys=%s",
                res.get("ok"), run_id or "(none)",
                list(res.keys()) if isinstance(res, dict) else type(res).__name__,
            )
            if not res.get("ok"):
                log.warning("[CHAT] chat.send rejected: %s", res.get("error"))
                await cloud_ws.send(json.dumps({
                    "request_id": request_id,
                    "data": {"error": "chat.send rejected", "detail": res.get("error")},
                }))
                return
        except asyncio.TimeoutError:
            log.warning("[CHAT] chat.send timeout (10s)")
            await cloud_ws.send(json.dumps({
                "request_id": request_id,
                "data": {"error": "chat.send timeout"},
            }))
            return

        full_text = ""
        thinking_text = ""
        tool_calls: list = []
        done = False
        try:
            while not done:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=180)
                except asyncio.TimeoutError:
                    break

                event_name = event.get("event", "")
                payload = event.get("payload", {})
                stream_val = payload.get("stream") if isinstance(payload, dict) else None

                # ── chat 事件：提取 tool_calls 和 message 中的文本 ──────
                if event_name == "chat":
                    state = payload.get("state") if isinstance(payload, dict) else None
                    if state == "final":
                        raw_tc = payload.get("tool_calls")
                        if isinstance(raw_tc, list) and raw_tc:
                            tool_calls = raw_tc
                        msg = payload.get("message") if isinstance(payload, dict) else None
                        chat_text = _extract_chat_event_text(msg)
                        if chat_text and not full_text:
                            full_text = chat_text
                            done = True
                    stream_event = {
                        "request_id": request_id,
                        "stream_event": {
                            # Cloud 侧会用 runId/sessionKey 做流式路由；这里必须带上，避免 strict 模式下丢事件导致“流式超时”
                            "runId": payload.get("runId") or payload.get("run_id") or "",
                            "sessionKey": payload.get("sessionKey") or session_key,
                            "type": "chat",
                            "data": payload,
                        },
                    }
                    try:
                        await cloud_ws.send(json.dumps(stream_event))
                    except Exception:
                        break
                    continue

                # ── agent 事件：思考/文本/工具进度/生命周期 ────────────
                stream = payload.get("stream", "")
                d = payload.get("data", {})

                # thinking/text 的增量字段在不同 Gateway 版本里结构不一，这里做兼容提取
                if stream == "thinking":
                    td = _extract_delta(payload if isinstance(payload, dict) else {})
                    if td:
                        thinking_text += td
                elif stream in ("text", "assistant"):
                    td = _extract_delta(payload if isinstance(payload, dict) else {})
                    if td:
                        full_text += td

                stream_event = {
                    "request_id": request_id,
                    "stream_event": {
                        "runId": payload.get("runId") or payload.get("run_id") or "",
                        "sessionKey": payload.get("sessionKey") or session_key,
                        "type": "text" if stream == "assistant" else stream,
                        "data": d,
                    },
                }
                try:
                    await cloud_ws.send(json.dumps(stream_event))
                except Exception:
                    break

                if stream == "lifecycle" and d.get("phase") == "end":
                    done = True

        finally:
            self._stream_listeners.pop(listener_id, None)

        log.info(
            "[CHAT <<] text_len=%d thinking_len=%d tools=%d reply=%s",
            len(full_text), len(thinking_text), len(tool_calls),
            (full_text[:200] + "...") if len(full_text) > 200 else (full_text or "(empty)"),
        )
        try:
            await cloud_ws.send(json.dumps({
                "request_id": request_id,
                "data": {
                    "content": full_text,
                    "thinking": thinking_text,
                    "toolCalls": tool_calls,
                    "done": True,
                },
            }))
        except Exception as e:
            log.warning(f"[stream] 回传最终结果失败（云端 WS 可能已断开）: {e}")

    async def send_chat_blocking(
        self, session_key: str, message: str,
        attachments: list | None = None,
    ) -> dict:
        """向 Gateway 发送 chat.send，收集完整结果后一次性返回（非流式）。"""
        processed_msg, local_attachments = _preprocess_file_references(message, session_key)
        merged_attachments = (attachments or []) + (local_attachments or []) or None

        log.info("[CHAT-SYNC >>] session=%s message=%s attachments=%d",
                 session_key, (processed_msg or "")[:200],
                 len(merged_attachments) if merged_attachments else 0)
        if not await self.ensure_connected():
            return {"error": "Gateway not connected"}

        self._req_id_counter += 1
        rid = str(self._req_id_counter)

        event_queue: asyncio.Queue = asyncio.Queue()
        self._stream_listener_seq += 1
        listener_id = f"l{int(time.time()*1000)}-{self._stream_listener_seq}"
        listener = self._StreamListener(
            id=listener_id,
            session_key=session_key,
            queue=event_queue,
            created_at=time.time(),
        )
        self._stream_listeners[listener_id] = listener

        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[rid] = future

        chat_params = {
            "sessionKey": session_key,
            "message": processed_msg,
            "idempotencyKey": f"rp-{int(time.time() * 1000)}",
        }
        if merged_attachments:
            chat_params["attachments"] = merged_attachments
        await self._ws.send(json.dumps({
            "type": "req", "id": rid, "method": "chat.send",
            "params": chat_params,
        }))

        try:
            res = await asyncio.wait_for(future, timeout=10)
            if not res.get("ok"):
                return {"error": "chat.send rejected", "detail": res.get("error")}
        except asyncio.TimeoutError:
            return {"error": "chat.send timeout"}

        full_text = ""
        thinking_text = ""
        try:
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=180)
                except asyncio.TimeoutError:
                    break

                payload = event.get("payload", {})
                stream = payload.get("stream", "")
                d = payload.get("data", {})

                if stream == "thinking":
                    td = _extract_delta(payload if isinstance(payload, dict) else {})
                    if td:
                        thinking_text += td
                elif stream in ("text", "assistant"):
                    td = _extract_delta(payload if isinstance(payload, dict) else {})
                    if td:
                        full_text += td
                elif stream == "lifecycle" and d.get("phase") == "end":
                    break
        finally:
            self._stream_listeners.pop(listener_id, None)

        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": full_text or "(no response)"},
                "finish_reason": "stop",
            }],
        }


def _extract_chat_params(params: dict) -> tuple[str, str, list | None]:
    """从请求 params 中提取 sessionKey、用户消息文本和 attachments。"""
    session_key = params.get(
        "sessionKey",
        f"agent:main:rp-{int(time.time())}",
    )
    messages = params.get("messages", [])
    message = ""
    if messages:
        last_user = [m for m in messages if m.get("role") == "user"]
        message = last_user[-1]["content"] if last_user else ""
    if not message:
        message = params.get("message", "")
    attachments = params.get("attachments")
    return session_key, message, attachments


async def _run_proxy(cloud_ws_url: str, device_id: str, gateway_token: str,
                     cloud_api_url: str = "", heartbeat_interval: int = 60,
                     firmware_version: str = "1.0.0"):
    """
    主循环：连接到云端 WebSocket，接收请求，路由到本地服务，回传结果。
    断线自动重连。同时启动周期性心跳后台任务。
    """
    gw_bridge = GatewayBridge(gateway_token)

    # 启动周期性心跳后台任务
    # 外部 Gateway（gw- 前缀）无 openclaw_device_state，跳过旧 heartbeat 流程；
    # 云端通过 WebSocket 连接状态感知在线，无需额外心跳
    _is_external_gw = device_id.startswith("gw-")
    if cloud_api_url and not _is_external_gw:
        from heartbeat import heartbeat_loop
        asyncio.create_task(heartbeat_loop(
            cloud_api_url=cloud_api_url,
            interval_sec=heartbeat_interval,
            firmware_version=firmware_version,
        ))
    elif not cloud_api_url:
        log.info("cloud_api_url 未配置，跳过周期性心跳")
    else:
        log.info("外部 Gateway 模式，跳过 heartbeat（云端以 WebSocket 连接感知在线状态）")

    async with httpx.AsyncClient() as client:
        while True:
            try:
                log.info(f"正在连接云端: {cloud_ws_url}")
                async with websockets.connect(
                    cloud_ws_url,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    log.info(f"已连接云端 (device_id={device_id})")

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                            request_id = msg.get("request_id", "")
                            function = msg.get("function", "")
                            params = msg.get("params", {})

                            _quiet_fns = ("chat/history", "sessions", "agents", "models", "api/files")
                            _is_quiet = any(q in function for q in _quiet_fns)
                            (log.debug if _is_quiet else log.info)(f"收到请求: id={request_id} fn={function}")

                            # 聊天类请求统一走 GatewayBridge（流式和非流式）
                            if function in STREAM_FUNCTIONS:
                                log.info(
                                    f"[chat] stream={params.get('stream')!r}  "
                                    f"_stream={params.get('_stream')!r}  "
                                    f"params_keys={list(params.keys())}"
                                )
                                want_stream = params.pop("stream", False) or params.pop("_stream", False)
                                session_key, message, attachments = _extract_chat_params(params)
                                # log.info(f"[chat] want_stream={want_stream}  sessionKey={session_key}  attachments={bool(attachments)}")

                                if want_stream:
                                    asyncio.create_task(
                                        gw_bridge.send_chat_and_stream(
                                            session_key, message, ws, request_id,
                                            attachments=attachments,
                                        )
                                    )
                                else:
                                    try:
                                        data = await gw_bridge.send_chat_blocking(
                                            session_key, message,
                                            attachments=attachments,
                                        )
                                        await ws.send(json.dumps({
                                            "request_id": request_id, "data": data,
                                        }))
                                    except Exception as e:
                                        await ws.send(json.dumps({
                                            "request_id": request_id,
                                            "data": {"error": str(e)},
                                        }))
                                continue

                            # 路由判断：含 "/" → HTTP 路径风格；否则 → Gateway RPC
                            is_http = any(function.startswith(entry[0]) for entry in ROUTE_TABLE) or "/" in function

                            if is_http:
                                if not _is_http_whitelisted(function):
                                    log.warning(f"HTTP 请求被白名单拦截: {function}")
                                    response = {
                                        "request_id": request_id,
                                        "data": {"error": "blocked", "detail": f"'{function}' 不在 HTTP 白名单中"},
                                    }
                                    await ws.send(json.dumps(response))
                                    continue

                                _gw_token = gateway_token or msg.get("gateway_token", "")
                                if _gw_token:
                                    params.setdefault("_headers", {}).setdefault(
                                        "Authorization", f"Bearer {_gw_token}"
                                    )

                                response = await _handle_request(
                                    client, request_id, function, params
                                )
                            else:
                                for k in list(params):
                                    if k.startswith("_"):
                                        params.pop(k)
                                try:
                                    data = await gw_bridge.rpc(function, params)
                                    response = {"request_id": request_id, "data": data}
                                except Exception as e:
                                    log.error(f"Gateway RPC 失败: {function}: {e}")
                                    response = {"request_id": request_id, "data": {"error": str(e)}}

                            await ws.send(json.dumps(response))
                            resp_data = response.get("data", {})
                            preview = ""
                            if isinstance(resp_data, dict):
                                content = resp_data.get("content") or resp_data.get("message") or ""
                                if not content and resp_data.get("choices"):
                                    msg = resp_data["choices"][0].get("message", {})
                                    content = msg.get("content", "")
                                preview = str(content)[:200]
                            elif isinstance(resp_data, str):
                                preview = resp_data[:200]
                            (log.debug if _is_quiet else log.info)(
                                f"已回复: id={request_id} fn={function}" + (f" | {preview}" if preview else "")
                            )

                        except json.JSONDecodeError:
                            log.warning("收到非 JSON 消息，忽略")
                        except Exception as e:
                            log.error(f"处理请求异常: {e}")
                            if request_id:
                                err_resp = {
                                    "request_id": request_id,
                                    "data": {"error": str(e)},
                                }
                                try:
                                    await ws.send(json.dumps(err_resp))
                                except Exception:
                                    pass

            except ConnectionClosed as e:
                log.warning(f"WebSocket 连接关闭: {e}，5s 后重连…")
            except Exception as e:
                log.warning(f"连接失败: {e}，5s 后重连…")

            await asyncio.sleep(5)


def _register_gateway(cloud_api_url: str) -> str:
    """外部 Gateway 向云端注册，获取配对码并打印到终端。
    返回 gw- 开头的 device_id（新分配或已持久化的）。

    注：仅供外部 Gateway 使用。Friday 物理设备走 heartbeat 配对，不调用此函数。
    """
    import urllib.error
    import urllib.request

    # 只从 gateway_identity.json 读取身份（外部 Gateway 专用存储）
    gw_identity = _load_gateway_identity()
    effective_id = gw_identity.get("device_id", "").strip()   # gw-xxx 或空
    device_secret = gw_identity.get("device_secret", "").strip()

    url = cloud_api_url.rstrip("/") + "/api/gateways/register"
    body: dict = {"source_type": "external", "runtime": "openclaw"}
    if effective_id:
        body["device_id"] = effective_id

    headers: dict = {"Content-Type": "application/json"}
    # 已有 device_secret → 刷新凭证（Bearer auth）
    if effective_id and device_secret:
        headers["Authorization"] = f"Bearer {device_secret}"

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="ignore")[:200]
        except Exception:
            pass
        log.warning(f"Gateway 注册失败: HTTP {e.code}  {body_text}")
        return effective_id
    except Exception as e:
        log.warning(f"Gateway 注册失败: {e}")
        return effective_id

    if not result.get("success"):
        log.warning(f"Gateway 注册响应异常: {result}")
        return effective_id

    new_id = (result.get("device_id") or "").strip()

    # 持久化云端分配的 device_id + device_secret（首次注册时返回 device_secret）
    if new_id:
        new_secret = result.get("device_secret", device_secret)
        _save_gateway_identity({"device_id": new_id, "device_secret": new_secret})
        if new_id != effective_id:
            log.info(f"云端分配新 device_id: {new_id}")

    effective_id = new_id or effective_id

    credential = result.get("credential") or {}
    code = credential.get("credential_code", "")
    expires_min = int(credential.get("expires_in_seconds", 1800)) // 60

    if code:
        formatted = f"{code[:4]}-{code[4:]}" if len(code) == 8 else code
        border = "=" * 54
        msg = (
            f"\n{border}\n"
            f"  配对码: {formatted}\n"
            f"  请在 Web 管理界面 > 添加外部 Gateway > 输入此码\n"
            f"  有效期：{expires_min} 分钟\n"
            f"{border}\n"
        )
        print(msg, flush=True)
        log.info(f"配对码: {formatted}（{expires_min} 分钟有效）")

    return effective_id


def _load_gateway_token(config: dict) -> str:
    """从环境变量、config.json、file-server .env 或 openclaw.json 中读取 OPENCLAW_TOKEN。"""
    env_token = os.environ.get("OPENCLAW_TOKEN", "").strip()
    if env_token:
        return env_token

    env_path = Path.home() / "moltbot-web" / "file-server" / ".env"
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENCLAW_TOKEN="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass

    openclaw_json = Path.home() / ".openclaw" / "openclaw.json"
    try:
        with open(openclaw_json) as f:
            cfg = json.load(f)
            return cfg.get("gateway", {}).get("auth", {}).get("token", "")
    except Exception:
        pass
    return ""


def start(cloud_api_url: Optional[str] = None, device_id: Optional[str] = None):
    """
    启动反向代理客户端（阻塞）。

    Args:
        cloud_api_url: 云端 HTTP 基地址（如 http://43.160.215.122:8764），
                       会自动转换成 ws:// 的 /proxy/{device_id} 路径。
        device_id:     设备 ID（如 ocl-xxx），默认从 config.json 或 device_state.json 读取。
    """
    config = _load_config()
    _init_routes(config)

    if not cloud_api_url:
        cloud_api_url = config.get("cloud_api_url", "").strip()
    if not cloud_api_url:
        log.error("cloud_api_url 未配置，请在 config.json 中设置")
        return

    if not device_id:
        device_id = _load_device_id(config)

    # 外部 Gateway 模式：device_id 为空或已有 gw- 开头的 → 走云端注册流程
    # Friday 物理设备（fri- 前缀）走旧 heartbeat 配对，不调用此注册接口
    is_external_gateway = (not device_id) or device_id.startswith("gw-") or bool(_load_gateway_identity().get("device_id"))
    if is_external_gateway:
        device_id = _register_gateway(cloud_api_url)
        if not device_id:
            log.error("外部 Gateway 注册失败，请检查网络或 cloud_api_url 配置")
            return

    if not device_id:
        log.error("device_id 未初始化，请在 config.json 中设置 device_id")
        return

    gateway_token = _load_gateway_token(config)
    log.info(f"[debug] gateway_token={'(empty)' if not gateway_token else gateway_token[:8]+'...'}")
    if not gateway_token:
        log.warning("OPENCLAW_TOKEN 未找到，流式对话功能将不可用")

    ws_url = cloud_api_url.replace("https://", "wss://").replace("http://", "ws://")
    ws_url = ws_url.rstrip("/") + f"/proxy/{device_id}"

    heartbeat_interval = int(config.get("heartbeat_interval_sec", 60))
    firmware_version = config.get("firmware_version", "1.0.0")

    log.info(f"反向代理启动: device_id={device_id}  cloud={ws_url}")
    asyncio.run(_run_proxy(
        ws_url, device_id, gateway_token,
        cloud_api_url=cloud_api_url,
        heartbeat_interval=heartbeat_interval,
        firmware_version=firmware_version,
    ))


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    start()
