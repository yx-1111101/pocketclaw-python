#!/usr/bin/env python3
"""
小程序 Skills 接口 HTTP 回归脚本

默认验证:
1) GET  /skills
2) GET  /skills/check
3) GET  /skills/{skill_id}

可选验证（会修改技能状态）:
4) POST /skills/{skill_id}/disable
5) POST /skills/{skill_id}/enable

环境变量:
  API_BASE_URL   默认 http://127.0.0.1:8000
  AUTH_TOKEN     必填（登录 token，不带 Bearer）
  DEVICE_ID      必填
  SKILL_ID       可选，不传则自动从 readySkills 取一个
  RUN_TOGGLE     可选，1/true/on 才执行 disable/enable（默认不执行）
"""

import os
import sys
from typing import Any

import httpx


API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "").strip()
DEVICE_ID = os.getenv("DEVICE_ID", "").strip()
SKILL_ID = os.getenv("SKILL_ID", "").strip()
RUN_TOGGLE = str(os.getenv("RUN_TOGGLE", "0")).strip().lower() in {"1", "true", "on", "yes"}


def fail(msg: str) -> None:
    print(f"❌ {msg}")
    sys.exit(1)


def ensure(cond: bool, msg: str) -> None:
    if not cond:
        fail(msg)


def call_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> tuple[int, dict[str, Any]]:
    url = f"{API_BASE_URL}{path}"
    resp = client.request(method, url, params=params, timeout=timeout)
    status = resp.status_code
    try:
        data = resp.json()
    except Exception:
        data = {"_raw": resp.text}
    return status, data


def main() -> None:
    if not AUTH_TOKEN:
        fail("缺少 AUTH_TOKEN")
    if not DEVICE_ID:
        fail("缺少 DEVICE_ID")

    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    with httpx.Client(headers=headers) as client:
        print("=== Skills HTTP Regression ===")
        print(f"API_BASE_URL: {API_BASE_URL}")
        print(f"DEVICE_ID: {DEVICE_ID}")
        print(f"RUN_TOGGLE: {RUN_TOGGLE}")

        # 1) list
        code, body = call_json(client, "GET", "/skills", params={"device_id": DEVICE_ID})
        ensure(code == 200, f"/skills HTTP {code}: {body}")
        ensure(bool(body.get("success")), f"/skills success=false: {body}")
        skills_payload = body.get("skills")
        if isinstance(skills_payload, dict):
            count = int(skills_payload.get("all_count") or 0)
        elif isinstance(skills_payload, list):
            count = len(skills_payload)
        else:
            count = 0
        print(f"✅ /skills ok, count={count}")

        # 2) check
        code, check = call_json(client, "GET", "/skills/check", params={"device_id": DEVICE_ID})
        ensure(code == 200, f"/skills/check HTTP {code}: {check}")
        ensure(bool(check.get("success")), f"/skills/check success=false: {check}")
        ready_skills = check.get("readySkills") if isinstance(check.get("readySkills"), list) else []
        print(
            "✅ /skills/check ok, "
            f"total={check.get('total')} ready={check.get('readyCount')} "
            f"missing={check.get('missingCount')} disabled={check.get('disabledCount')}"
        )

        # 3) detail
        skill_id = SKILL_ID or (ready_skills[0] if ready_skills else "")
        ensure(bool(skill_id), "未找到可用 skill_id，请通过 SKILL_ID 指定")
        code, detail = call_json(client, "GET", f"/skills/{skill_id}", params={"device_id": DEVICE_ID})
        ensure(code == 200, f"/skills/{{id}} HTTP {code}: {detail}")
        ensure(bool(detail.get("success")), f"/skills/{{id}} success=false: {detail}")
        skill = detail.get("skill") if isinstance(detail.get("skill"), dict) else {}
        print(
            "✅ /skills/{id} ok, "
            f"id={skill.get('id')} status={skill.get('status')} enabled={skill.get('enabled')}"
        )

        # 4/5) toggle (optional)
        if RUN_TOGGLE:
            code, disable = call_json(
                client,
                "POST",
                f"/skills/{skill_id}/disable",
                params={"device_id": DEVICE_ID},
            )
            ensure(code == 200, f"/skills/{{id}}/disable HTTP {code}: {disable}")
            ensure(bool(disable.get("success")), f"/skills/{{id}}/disable success=false: {disable}")
            print("✅ disable ok")

            code, enable = call_json(
                client,
                "POST",
                f"/skills/{skill_id}/enable",
                params={"device_id": DEVICE_ID},
            )
            ensure(code == 200, f"/skills/{{id}}/enable HTTP {code}: {enable}")
            ensure(bool(enable.get("success")), f"/skills/{{id}}/enable success=false: {enable}")
            print("✅ enable ok")

        print("🎉 回归通过")


if __name__ == "__main__":
    main()
