"""llm_proxy 独立服务入口"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from llm_proxy.config import REDIS_HOST, REDIS_PORT, REDIS_DB, PORT
from llm_proxy.redis_db import init_db
from llm_proxy.providers import init_providers
from llm_proxy.router import router

init_db(REDIS_HOST, REDIS_PORT, REDIS_DB)
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
