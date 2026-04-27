#!/usr/bin/env python3
"""
周期性心跳模块

在 pocketclaw-device 的主循环中以异步任务运行，每隔 heartbeat_interval_sec 秒
向云端发送一次 HTTP 心跳（POST /devices/heartbeat）。

职责：
  - 设备在线状态上报
  - 首次注册（携带 device_secret_hash）
  - 配对码 hash 上报（供云端匹配小程序绑定申请）
  - 从云端响应同步 claimed 状态（云端是权威来源）
"""

import asyncio
import hashlib
import hmac as _hmac
import json
import logging
import time
from typing import Optional

import openclaw_device_state as ds

log = logging.getLogger("pocketclaw-device.heartbeat")


# ─── 工具函数 ─────────────────────────────────────────────────────────────────

def _sign(device_secret: str, device_id: str, timestamp: int) -> str:
    message = f"{device_id}:{timestamp}".encode("utf-8")
    key = device_secret.encode("utf-8")
    return _hmac.new(key, message, hashlib.sha256).hexdigest()


def _sha256hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ─── 单次心跳发送 ─────────────────────────────────────────────────────────────

async def _send_heartbeat_once(
    cloud_api_url: str,
    state: dict,
    firmware_version: str = "1.0.0",
) -> bool:
    """
    发送一次心跳（异步，在 executor 中执行阻塞 HTTP 调用）。
    返回 True = 成功。
    """
    import urllib.error
    import urllib.request

    device_id = state.get("device_id", "").strip()
    device_secret = state.get("device_secret", "").strip()
    if not device_id or not device_secret:
        log.debug("device_id 或 device_secret 缺失，跳过心跳")
        return False

    timestamp = int(time.time())
    signature = _sign(device_secret, device_id, timestamp)

    pairing_code = state.get("pairing_code")
    pairing_expires = state.get("pairing_code_expires", 0)
    if pairing_code and time.time() < pairing_expires:
        code_hash = _sha256hex(pairing_code)
        code_expires = int(pairing_expires)
    else:
        code_hash = None
        code_expires = None

    body: dict = {
        "device_id": device_id,
        "public_url": "",
        "pairing_code_hash": code_hash,
        "pairing_code_expires": code_expires,
        "firmware_version": firmware_version,
        "timestamp": timestamp,
    }

    is_first = not bool(state.get("cloud_registered", False))
    if is_first:
        body["device_secret_hash"] = _sha256hex(device_secret)
        log.info("首次向云端注册，携带 device_secret_hash")

    url = cloud_api_url.rstrip("/") + "/devices/heartbeat"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Device-Id": device_id,
            "X-Timestamp": str(timestamp),
            "Authorization": f"HMAC-SHA256 {signature}",
        },
        method="POST",
    )

    loop = asyncio.get_event_loop()

    def _do_request():
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body_text = ""
            try:
                body_text = e.read().decode("utf-8", errors="ignore")[:200]
            except Exception:
                pass
            log.warning(f"心跳 HTTP {e.code}: {e.reason}  {body_text}")
            return None
        except urllib.error.URLError as e:
            log.warning(f"心跳网络错误: {e}")
            return None
        except Exception as e:
            log.error(f"心跳发送失败: {e}")
            return None

    result = await loop.run_in_executor(None, _do_request)

    if result and result.get("success"):
        if is_first:
            try:
                ds.mark_cloud_registered()
            except Exception as e:
                log.warning(f"标记 cloud_registered 失败: {e}")
        claimed = result.get("claimed")
        if claimed is not None:
            try:
                old = ds.get_claimed()
                if old != bool(claimed):
                    ds.set_claimed(bool(claimed))
            except Exception as e:
                log.warning(f"同步 claimed 状态失败: {e}")
        return True

    if result:
        log.warning(f"云端心跳响应异常: {result}")
    return False


# ─── 周期心跳任务（供 reverse_proxy 调用）────────────────────────────────────

async def heartbeat_loop(
    cloud_api_url: str,
    interval_sec: int = 60,
    firmware_version: str = "1.0.0",
):
    """
    周期性心跳任务，在 asyncio 事件循环中作为后台 Task 运行。

    每隔 interval_sec 秒读取最新的 device_state，发送一次心跳，
    并从云端响应同步 claimed 状态。
    """
    log.info(f"心跳任务启动（间隔 {interval_sec}s）")
    while True:
        try:
            state = ds.load()
            if state.get("device_id"):
                await _send_heartbeat_once(cloud_api_url, state, firmware_version)
            else:
                log.debug("device_id 未初始化，跳过本次心跳")
        except Exception as e:
            log.error(f"心跳任务异常: {e}")
        await asyncio.sleep(interval_sec)
