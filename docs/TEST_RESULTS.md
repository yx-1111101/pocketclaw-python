# OpenClaw Gateway WebSocket RPC 测试结果

> 测试时间: 2026-03-20
> Token: 39353e14566ccc5caf8f6d588366b27a81f005e28b68c

---

## ✅ 成功列表 (8/8)

| API | 方法 | CLI 测试结果 |
|-----|------|--------------|
| chat.send | POST | ✅ 正常 |
| chat.history | GET | ✅ 正常 |
| sessions.list | GET | ✅ 正常 |
| skills.list | GET | ✅ 正常 (23个可用) |
| models.list | GET | ✅ 正常 (5个模型) |
| cron.list | GET | ✅ 正常 (无任务) |
| channels.status | GET | ✅ 正常 |
| config.get | GET | ✅ 正常 |

---

## ❌ 失败列表 (0/8)

无

---

## CLI 实际输出

### sessions.list
```
Session                      Channel     Unread  Last Active
agent:main:main              🤖 agent    0       5 minutes ago
telegram:8773269994:8773269994  ✈️ telegram  0       4 minutes ago
telegram:8773269994:product  ✈️ telegram  0       2 hours ago
```

### skills.list (部分)
```
Total: 64 | ✓ Ready: 23 | ✗ Missing: 41

Ready:
  📦 feishu-doc, feishu-drive, feishu-perm, feishu-wiki
  📦 qqbot-cron, qqbot-media
  📦 clawhub, github, weather
  🧩 coding-agent
  ...
```

### models.list
```
Default: minimax/MiniMax-M2.5
Fallbacks: anthropic/claude-sonnet-4-6, minimax/MiniMax-M2.5
Configured (5):
  - anthropic/claude-sonnet-4-6
  - minimax/MiniMax-M2.5
  - minimax-portal/MiniMax-M2.5
  - minimax-portal/MiniMax-M2.5-highspeed
  - minimax-portal/MiniMax-M2.5-Lightning
```

### cron.list
```
No cron jobs.
```

---

## 测试脚本

运行测试脚本:
```bash
pip install websocket-client
python3 scripts/test_gateway_rpc.py
```

脚本位置: `scripts/test_gateway_rpc.py`
