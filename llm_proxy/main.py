"""llm_proxy 独立服务入口"""
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_proxy.config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB, REDIS_HOST, REDIS_PORT, REDIS_DB, PORT
from llm_proxy.redis_db import init_cache
from llm_proxy.db_client import init_db
from llm_proxy.providers import init_providers
from llm_proxy.router import router

init_db(MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB)
init_cache(REDIS_HOST, REDIS_PORT, REDIS_DB)
init_providers()

app = FastAPI(title="LLM Proxy Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
