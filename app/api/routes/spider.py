"""
后台采集管理路由
- POST /api/v1/spider/collect 提交后台采集任务(异步非阻塞)
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as redis

from app.core.config import settings
from app.core.database import get_db, get_redis
from app.core.response import error_response, success_response
from app.models.film_source import FilmSource
from app.services.spider import (
    cache_to_redis,
    collect_pages_concurrently,
    generate_hash_key,
)

router = APIRouter(prefix="/api/v1/spider", tags=["spider"])

# ⚠️ 修复 1: 全局集合持有后台任务引用，防止 GC 静默取消
_background_tasks: set[asyncio.Task] = set()


class CollectRequest(BaseModel):
    """采集请求体"""
    source_id: str = Field(..., description="采集源ID(对应 film_source.id)")
    hours: int = Field(0, ge=0, le=720, description="增量小时数,0 表示全量")
    pages: int = Field(5, ge=1, le=100, description="采集页数")


async def _run_collect_task(
    source_id: str,
    hours: int,
    pages: int,
    redis_client: redis.Redis,
) -> None:
    """后台实际执行的采集任务"""
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        stmt = select(FilmSource).where(FilmSource.id == source_id)
        source = (await db.execute(stmt)).scalar_one_or_none()
        if source is None or not source.is_active:
            return

        movies = await collect_pages_concurrently(
            source=source,
            pages=pages,
            hours=hours,
            settings=settings.spider,
        )

        for m in movies:
            name = m.get("vod_name") or m.get("title") or ""
            m["mid"] = generate_hash_key(name)

        await cache_to_redis(
            redis_client=redis_client,
            source_id=source.id,
            is_master=source.is_master,
            movie_list=movies,
        )


@router.post("/collect")
async def collect(
    body: CollectRequest,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """提交后台采集任务(非阻塞)。"""
    stmt = select(FilmSource).where(FilmSource.id == body.source_id)
    source = (await db.execute(stmt)).scalar_one_or_none()
    if source is None:
        return error_response("采集源不存在")
    if not source.is_active:
        return error_response("采集源已禁用")

    task = asyncio.create_task(
        _run_collect_task(
            source_id=body.source_id,
            hours=body.hours,
            pages=body.pages,
            redis_client=redis_client,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)  # ⚠️ 修复 1: 任务完成后自动从集合移除
    return success_response({"msg": "采集任务已提交后台"})
