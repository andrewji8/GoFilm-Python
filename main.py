"""
GoFilm-Python 应用入口

- FastAPI lifespan 管理调度器、Redis、数据库连接池的生命周期
- 统一注册所有业务路由
- 启动: uvicorn main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes.film import router as film_router
from app.api.routes.spider import router as spider_router
from app.core.config import settings
from app.core.database import Base, close_redis, dispose_engine, engine
from app.core.response import success_response
from app.services.scheduler import scheduler, start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动 / 关闭生命周期"""
    logger.info("=" * 60)
    logger.info("GoFilm-Python 启动中 ... env=%s", settings.app_env)
    logger.info("MySQL: %s:%s/%s", settings.mysql.host, settings.mysql.port, settings.mysql.db)
    logger.info("Redis: %s:%s/%s", settings.redis.host, settings.redis.port, settings.redis.db)
    logger.info("=" * 60)

    # 1. 自动创建数据库表(首次运行或新增表时使用)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表结构校验/创建完成")
    except Exception as exc:
        logger.exception("创建数据库表失败: %s", exc)
        raise

    # 2. 启动 APScheduler 定时任务
    start_scheduler()

    yield

    logger.info("GoFilm-Python 正在关闭 ...")
    try:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler 已关闭")
    except Exception as exc:
        logger.exception("关闭调度器异常: %s", exc)

    try:
        await close_redis()
        logger.info("Redis 连接已释放")
    except Exception as exc:
        logger.exception("关闭 Redis 异常: %s", exc)

    try:
        await dispose_engine()
        logger.info("数据库连接池已释放")
    except Exception as exc:
        logger.exception("释放数据库连接池异常: %s", exc)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="GoFilm Python 后端重构版 (FastAPI + SQLAlchemy 2.0)",
    lifespan=lifespan,
)


@app.get("/health", tags=["meta"])
async def health():
    return success_response({"status": "ok"})


app.include_router(film_router)
app.include_router(spider_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "dev"),
    )
