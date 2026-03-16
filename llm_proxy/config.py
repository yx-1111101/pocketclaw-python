"""llm_proxy 独立配置 — 从环境变量读取，不依赖 app/"""
import os

# Supabase（设备数据主存储）
SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "https://irbnhwtyhzltpjiuuyql.supabase.co")
SUPABASE_KEY: str = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlyYm5od3R5aHpsdHBqaXV1eXFsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzMzMDc3NCwiZXhwIjoyMDg4OTA2Nzc0fQ.u0qwNGdrtniSxIlihYKpbM6HWh10UXlxPCE4y8-8Blk")

# Redis（设备行缓存，60s TTL）
REDIS_HOST: str = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB: int = int(os.environ.get("REDIS_DB", "0"))

PORT: int = int(os.environ.get("LLM_PROXY_PORT", "8765"))
