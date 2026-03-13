# LLM Proxy Service

LLM 代理服务，提供设备认证和多提供商路由功能。

## 功能特性

1. **HMAC-SHA256 设备认证**：基于设备 ID 和密钥的签名认证
2. **多提供商支持**：支持智谱 AI、OpenAI 等多个 LLM 提供商
3. **用户设备绑定验证**：确保请求来自已绑定的设备
4. **统一接口**：提供标准的聊天补全接口

## API 接口

### 1. 聊天补全

```http
POST /llm/chat/completions
Content-Type: application/json
X-Device-Id: ocl-3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e
X-Timestamp: 1741593600
Authorization: HMAC-SHA256 <signature_hexstring>

{
  "messages": [
    {"role": "user", "content": "你好"}
  ],
  "model": "glm-4",
  "provider": "zhipu",
  "temperature": 0.7,
  "max_tokens": 2000
}
```

**响应**：
```json
{
  "success": true,
  "data": {
    "id": "...",
    "choices": [
      {
        "message": {
          "role": "assistant",
          "content": "你好！有什么我可以帮助你的吗？"
        }
      }
    ]
  }
}
```

### 2. 列出提供商

```http
GET /llm/providers
```

**响应**：
```json
{
  "success": true,
  "providers": ["zhipu"]
}
```

### 3. 健康检查

```http
GET /llm/health
```

**响应**：
```json
{
  "ok": true,
  "service": "llm_proxy"
}
```

## 认证方式

### HMAC-SHA256 签名算法

```python
import hmac
import hashlib
import time

device_id = "ocl-3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e"
device_secret = "your_device_secret"
timestamp = int(time.time())

# 构造消息
message = f"{device_id}:{timestamp}"

# 计算签名
signature = hmac.new(
    device_secret.encode('utf-8'),
    message.encode('utf-8'),
    hashlib.sha256
).hexdigest()

# 请求头
headers = {
    "X-Device-Id": device_id,
    "X-Timestamp": str(timestamp),
    "Authorization": f"HMAC-SHA256 {signature}"
}
```

### 请求头说明

| Header | 说明 |
|--------|------|
| X-Device-Id | 设备 ID |
| X-Timestamp | Unix 时间戳（秒），需在服务器时间 ±300 秒内 |
| Authorization | `HMAC-SHA256 <signature>` 格式 |

## 配置

在 `app/config.py` 中配置 LLM 提供商：

```python
LLM_PROVIDERS = {
    "zhipu": {
        "api_key": os.getenv("ZHIPU_API_KEY", ""),
        "base_url": "https://open.bigmodel.cn/api/paas/v4"
    }
}
```

或通过环境变量：

```bash
export ZHIPU_API_KEY="your_api_key"
export ZHIPU_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
```

## 数据库要求

设备表需要包含以下字段：

- `device_id`: 设备 ID（字符串）
- `device_secret`: 设备密钥明文（字符串）
- `device_secret_hash`: 设备密钥 SHA256 哈希（字符串，可选）

设备绑定表：

- `device_id`: 设备 ID（外键）
- `user_id`: 用户 ID（外键）
- `role`: 角色（如 "owner"）

## 安全注意事项

1. **密钥存储**：当前实现要求数据库存储明文 `device_secret`，用于验证签名
2. **时间戳验证**：防止重放攻击，时间戳容差为 ±300 秒
3. **HTTPS**：生产环境必须使用 HTTPS
4. **密钥轮换**：建议定期更换设备密钥

## 扩展提供商

在 `llm_proxy/providers.py` 中添加新的提供商：

```python
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
    self.api_key = api_key
        self.base_url = base_url

    async def chat_completion(self, messages: list, model: str = "gpt-4", **kwargs):
        # 实现 OpenAI API 调用
        pass

# 在 init_providers 中注册
def init_providers(config):
    if "openai" in config:
        registry.register("openai", OpenAIProvider(...))
```
