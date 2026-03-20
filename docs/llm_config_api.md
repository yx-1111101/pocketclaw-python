# LLM Config API 文档

管理 `llm/config/` 中 `sources.json` 和 `models.json` 的 REST 接口。
每次写入配置后，自动同步更新 `~/.openclaw/openclaw.json`（providers 列表与模型白名单）。

**注意**: `models.json` 文件采用新的嵌套结构 `sources -> source -> models -> model`，但 API 仍返回扁平化的模型列表以保持兼容性。

- **Base URL**: `http://localhost:20002`
- **交互式文档**: `http://localhost:20002/docs`（Swagger UI）
- **Content-Type**: `application/json`

---

## 目录

| # | 接口 | 方法 | 路径 |
|---|------|------|------|
| 1.1 | [读取配置](#11-读取配置) | `GET` | `/llm/api/config` |
| 1.2 | [新增源](#12-新增源) | `POST` | `/llm/api/sources/{source_name}` |
| 1.3 | [删除源](#13-删除源) | `DELETE` | `/llm/api/sources/{source_name}` |
| 1.4 | [复制源](#14-复制源) | `POST` | `/llm/api/sources/{source_name}/copy` |
| 1.5 | [修改源](#15-修改源) | `PUT` | `/llm/api/sources/{source_name}` |
| 1.6 | [新增模型（批量）](#16-新增模型批量) | `POST` | `/llm/api/models` |
| 1.7 | [删除模型（批量）](#17-删除模型批量) | `DELETE` | `/llm/api/models` |
| 1.8 | [更改模型（批量覆写）](#18-更改模型批量覆写) | `PUT` | `/llm/api/models` |
| 1.9 | [收藏/取消收藏模型](#19-收藏取消收藏模型) | `PATCH` | `/llm/api/models/{model_id}/favorite` |

---

## 数据结构

### SourceEntry

源（Provider）的配置对象。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `base_url` | string | ✅ | — | API 端点的基础 URL |
| `api_key` | string | | `""` | 明文 API Key（与 `api_key_env` 二选一） |
| `api_key_env` | string | | `""` | 从环境变量读取 API Key 的变量名（优先级高于 `api_key`） |
| `request_type` | string | | `"openai"` | 协议类型：`"openai"` 或 `"anthropic"` |
| `timeout` | integer | | `120` | 该源的默认 HTTP 超时（秒） |

### ModelEntry

模型的配置对象。

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source` | string | ✅ | — | 所属源的名称（必须在 sources.json 中存在） |
| `model` | string | | `""` | 转发给上游的实际模型名，留空则使用模型 ID 本身 |
| `currency` | string | | `"USD"` | 计费货币 |
| `input` | float | | `0.0` | 输入 Token 单价（每 1M tokens） |
| `output` | float | | `0.0` | 输出 Token 单价（每 1M tokens） |
| `timeout` | integer\|null | | `null` | 该模型的 HTTP 超时覆盖（秒），`null` 则继承源的超时 |
| `reasoning` | boolean | | `false` | 是否为推理模型（影响 openclaw 的模型展示） |
| `input_types` | string[] | | `["text"]` | 支持的输入类型，可选值：`"text"`、`"image"` |
| `contextWindow` | integer | | `131072` | 上下文窗口大小（tokens） |
| `maxTokens` | integer | | `16384` | 最大输出 tokens |
| `favorite` | boolean | | `false` | 是否为收藏模型 |

---

## 1.1 读取配置

返回当前 `sources.json` 和 `models.json` 的完整内容。

```
GET /llm/api/config
```

**响应示例**

```json
{
  "sources": {
    "zhizengzeng": {
      "base_url": "https://api.zhizengzeng.com/v1",
      "api_key": "sk-xxx",
      "request_type": "openai",
      "timeout": 120
    }
  },
  "models": {
    "gpt-4o": {
      "source": "zhizengzeng",
      "currency": "USD",
      "input": 2.5,
      "output": 10.0,
      "timeout": 120,
      "reasoning": false,
      "input_types": ["text"],
      "contextWindow": 131072,
      "maxTokens": 16384
    }
  }
}
```

---

## 1.2 新增源

新增一个源配置。若源名称已存在，返回 `409`。

```
POST /llm/api/sources/{source_name}
```

**路径参数**

| 参数 | 说明 |
|------|------|
| `source_name` | 源的唯一标识名，如 `openai`、`my-provider` |

**请求体** — [SourceEntry](#sourceentry)

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key_env": "OPENAI_API_KEY",
  "request_type": "openai",
  "timeout": 120
}
```

**响应示例**

```json
{
  "ok": true,
  "source": "openai"
}
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `409` | 源名称已存在，请使用 PUT 修改 |

---

## 1.3 删除源

删除指定源，**级联删除** `models.json` 中所有引用该源的模型，同时从 `openclaw.json` 中移除对应 provider 及其模型白名单。

```
DELETE /llm/api/sources/{source_name}
```

**路径参数**

| 参数 | 说明 |
|------|------|
| `source_name` | 要删除的源名称 |

**响应示例**

```json
{
  "ok": true,
  "deleted": "openai",
  "deleted_models": ["gpt-4o", "gpt-4o-mini"]
}
```

> `deleted_models` 为本次级联删除的模型 ID 列表，若该源下无模型则为空数组。

**错误码**

| 状态码 | 原因 |
|--------|------|
| `404` | 源不存在 |

---

## 1.4 复制源

将一个源的配置深拷贝为新名称。新名称默认为 `{source_name}-copy`，可通过 query 参数指定。

```
POST /llm/api/sources/{source_name}/copy?new_name={new_name}
```

**路径参数**

| 参数 | 说明 |
|------|------|
| `source_name` | 要复制的源名称 |

**Query 参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `new_name` | string | | 目标源名称，留空则自动追加 `-copy` 后缀 |

**请求示例**

```
POST /llm/api/sources/zhizengzeng/copy?new_name=zhizengzeng-backup
```

**响应示例**

```json
{
  "ok": true,
  "copied_to": "zhizengzeng-backup"
}
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `404` | 源不存在 |
| `409` | 目标名称已存在 |

---

## 1.5 修改源

全量覆写一个源的配置。若源不存在，返回 `404`（创建请用 POST）。

```
PUT /llm/api/sources/{source_name}
```

**路径参数**

| 参数 | 说明 |
|------|------|
| `source_name` | 要修改的源名称 |

**请求体** — [SourceEntry](#sourceentry)

```json
{
  "base_url": "https://api.openai.com/v1",
  "api_key": "sk-new-key",
  "request_type": "openai",
  "timeout": 180
}
```

**响应示例**

```json
{
  "ok": true,
  "source": "openai"
}
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `404` | 源不存在，请用 POST 创建 |

---

## 1.6 新增模型（批量）

批量新增模型。若任何模型 ID 已存在，整体返回 `409`（不会部分写入）。

```
POST /llm/api/models
```

**请求体**

```json
{
  "models": {
    "<model_id>": { ...ModelEntry },
    "<model_id>": { ...ModelEntry }
  }
}
```

**请求示例**

```json
{
  "models": {
    "gpt-5-mini": {
      "source": "zhizengzeng",
      "currency": "USD",
      "input": 0.30,
      "output": 1.20,
      "timeout": 60
    },
    "gpt-5-nano": {
      "source": "zhizengzeng",
      "currency": "USD",
      "input": 0.10,
      "output": 0.40,
      "timeout": 60
    }
  }
}
```

**响应示例**

```json
{
  "ok": true,
  "added": ["gpt-5-mini", "gpt-5-nano"]
}
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `400` | 指定的 `source` 在 sources.json 中不存在 |
| `409` | 一个或多个模型 ID 已存在，请使用 PUT 覆写 |

---

## 1.7 删除模型（批量）

批量删除模型。找不到的 ID 不会报错，会记录在 `not_found` 字段中。

```
DELETE /llm/api/models
```

**请求体**

```json
{
  "model_ids": ["<model_id>", "<model_id>"]
}
```

**请求示例**

```json
{
  "model_ids": ["gpt-5-mini", "gpt-5-nano", "nonexistent-model"]
}
```

**响应示例**

```json
{
  "ok": true,
  "deleted": ["gpt-5-mini", "gpt-5-nano"],
  "not_found": ["nonexistent-model"]
}
```

> **注意**：若被删除的模型恰好是 `openclaw.json` 中 `agents.defaults.model.primary`，该字段会被自动清空。

---

## 1.8 更改模型（批量覆写）

批量覆写模型配置。已存在的模型会被完整替换，不存在的模型会被新建。

```
PUT /llm/api/models
```

**请求体**（与 1.6 相同结构）

```json
{
  "models": {
    "<model_id>": { ...ModelEntry }
  }
}
```

**请求示例** — 更新定价并添加图片支持

```json
{
  "models": {
    "gpt-4o": {
      "source": "zhizengzeng",
      "currency": "USD",
      "input": 2.00,
      "output": 8.00,
      "timeout": 120,
      "input_types": ["text", "image"],
      "contextWindow": 128000,
      "maxTokens": 16384
    },
    "claude-opus-4-6": {
      "source": "zhizengzeng",
      "currency": "USD",
      "input": 5.00,
      "output": 25.00,
      "timeout": 180,
      "reasoning": true
    }
  }
}
```

**响应示例**

```json
{
  "ok": true,
  "upserted": ["gpt-4o", "claude-opus-4-6"]
}
```

**错误码**

| 状态码 | 原因 |
|--------|------|
| `400` | 指定的 `source` 在 sources.json 中不存在 |

---

## 1.9 收藏/取消收藏模型

设置或取消模型的收藏状态。收藏的模型会在 `models.json` 中标记 `favorite: true`。

```
PATCH /llm/api/models/{model_id}/favorite
```

**路径参数**

| 参数 | 说明 |
|------|------|
| `model_id` | 要操作的模型 ID |

**请求体**

```json
{
  "action": "favorite"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | ✅ | 操作类型：`"favorite"` 收藏，`"unfavorite"` 取消收藏 |

**请求示例**

```bash
# 收藏模型
curl -X PATCH http://localhost:20002/llm/api/models/gpt-4o/favorite \
  -H "Content-Type: application/json" \
  -d '{"action": "favorite"}'

# 取消收藏
curl -X PATCH http://localhost:20002/llm/api/models/gpt-4o/favorite \
  -H "Content-Type: application/json" \
  -d '{"action": "unfavorite"}'
```

**响应示例**

```json
{
  "ok": true,
  "model": "gpt-4o",
  "favorite": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | boolean | 操作是否成功 |
| `model` | string | 操作的模型 ID |
| `favorite` | boolean | 当前收藏状态（`true` 已收藏，`false` 未收藏） |

**错误码**

| 状态码 | 原因 |
|--------|------|
| `400` | `action` 参数无效（非 `favorite` 或 `unfavorite`） |
| `400` | `model_id` 格式无效（含非法字符或为空） |
| `404` | 模型不存在 |

---

## 错误处理

所有接口都包含完善的错误处理：

### 通用错误

| 状态码 | 场景 | 示例 |
|--------|------|------|
| `400` | 请求参数无效 | 空的 `source_name`、含 `/` 的名称、空的批量操作列表 |
| `404` | 资源不存在 | 源不存在、模型不存在 |
| `409` | 资源冲突 | 新增已存在的源/模型、复制到已存在的目标名称 |
| `500` | 服务器内部错误 | JSON 文件写入失败 |
| `503` | 服务不可用 | JSON 文件读取失败（文件损坏） |

### 名称格式校验

`source_name` 和 `model_id` 必须符合以下规则：
- 不能为空或纯空格
- 只能包含字母、数字、连字符（`-`）、下划线（`_`）、点（`.`）
- **不能包含斜杠（`/`）**，因为会与 openclaw.json 白名单格式 `source/model` 冲突

**无效示例**：`""`, `"  "`, `"a/b"`, `"foo bar"`, `"x!y"`
**有效示例**：`"openai"`, `"my-provider_v2"`, `"gpt-4.0"`

---

## openclaw.json 同步说明

所有写操作完成后，会自动同步 `~/.openclaw/openclaw.json`：

| 操作 | 同步行为 |
|------|----------|
| 新增/修改源 | 更新 `models.providers[source_name]`，重建该源下所有模型列表 |
| 删除源 | 移除 `models.providers[source_name]`，**同时级联删除** models.json 中属于该源的所有模型及其白名单条目 |
| 新增模型 | 追加到对应 provider 的 models 列表，加入 `agents.defaults.models` 白名单 |
| 删除模型 | 从 provider models 列表移除，从白名单移除；若为 primary 则清空 |
| 覆写模型 | 全量重建受影响 provider 的 models 列表，同步白名单 |

### model-router provider 的保留

`model-router` provider（路由虚拟模型 `auto` / `eco` / `premium` / `agentic`）是固定内置配置，**不来自 sources/models json**，每次同步时都会被无条件写入，不会被任何源或模型操作覆盖或删除：

```json
{
  "models": {
    "providers": {
      "model-router": {
        "baseUrl": "http://localhost:20001/v1",
        "apiKey": "local",
        "api": "openai-completions",
        "models": [
          { "id": "auto",     "name": "Router Auto" },
          { "id": "eco",      "name": "Router Eco" },
          { "id": "premium",  "name": "Router Premium" },
          { "id": "agentic",  "name": "Router Agentic" }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "models": {
        "model-router/auto":    {},
        "model-router/eco":     {},
        "model-router/premium": {},
        "model-router/agentic": {}
      }
    }
  }
}
```

### 用户自定义模型白名单格式

白名单 key 格式为 `{source_name}/{model_id}`，例如：

```json
{
  "agents": {
    "defaults": {
      "models": {
        "zhizengzeng/gpt-4o": {},
        "zhizengzeng/claude-opus-4-6": {}
      }
    }
  }
}
```

---

## 启动服务

```bash
cd /llm
python3 -m api.run
# 或
python3 api/run.py
```

服务默认监听 `0.0.0.0:20002`。
