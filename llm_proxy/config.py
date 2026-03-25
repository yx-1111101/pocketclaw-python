"""llm_proxy 独立配置 — 从环境变量读取，不依赖 app/"""
import os

# MySQL（设备数据主存储）
MYSQL_HOST: str = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT: int = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_USER: str = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD: str = os.environ.get("MYSQL_PASSWORD", "")
MYSQL_DB: str = os.environ.get("MYSQL_DB", "openfriday")

# Redis（设备行缓存，60s TTL）
REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))

PORT: int = int(os.environ.get("LLM_PROXY_PORT", "8765"))
