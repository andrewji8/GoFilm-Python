"""
数据库 & Redis 异步客户端初始化
- SQLAlchemy 2.0 异步引擎 + AsyncSession 工厂
- redis.asyncio.from_url 模块级单例(自带连接池)
- FastAPI 依赖注入函数 get_db / get_redis
"""
from typing import AsyncGenerator

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


engine = create_async_engine(
    settings.mysql.async_url,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖:每个请求一个 Session,请求结束自动关闭"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


redis_client: redis.Redis = redis.from_url(
    settings.redis.url,
    encoding="utf-8",
    decode_responses=True,
    max_connections=50,
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """FastAPI 依赖:直接 yield 全局单例客户端,不重复创建"""
    yield redis_client


async def close_redis() -> None:
    """应用关闭时释放 Redis 连接"""
    await redis_client.aclose()


async def dispose_engine() -> None:
    """应用关闭时释放数据库连接池"""
    await engine.dispose()
