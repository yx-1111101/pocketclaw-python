"""配置管理"""
import os

# MySQL 配置（持久化存储）
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DB = os.getenv("MYSQL_DB", "openfriday")

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
