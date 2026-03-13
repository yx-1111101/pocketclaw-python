"""配置管理"""
import os

# Supabase 配置（持久化存储）
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://irbnhwtyhzltpjiuuyql.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlyYm5od3R5aHpsdHBqaXV1eXFsIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzMzMDc3NCwiZXhwIjoyMDg4OTA2Nzc0fQ.u0qwNGdrtniSxIlihYKpbM6HWh10UXlxPCE4y8-8Blk")

# Redis 配置（可选，用于 redis_db 后端）
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# 微信配置
WECHAT_APP_ID = os.getenv("WECHAT_APP_ID", "wxc6ee0aee83c794e7")
WECHAT_APP_SECRET = os.getenv("WECHAT_APP_SECRET", "1264e0e7f7a90e65a92061355873bb37")

# 服务配置
PORT = int(os.getenv("PORT", "8764"))
DEFAULT_TOKEN = os.getenv("GATEWAY_TOKEN", "39353e14566ccc5caf8f6d588366b27a81f005e28b81b68c")
