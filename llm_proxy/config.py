"""llm_proxy 独立配置 — 从环境变量读取，不依赖 app/"""
import os

REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))

PORT: int = int(os.environ.get("LLM_PROXY_PORT", "8765"))
