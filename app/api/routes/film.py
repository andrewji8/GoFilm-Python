"""
前端展示相关路由
- GET /api/v1/movies       分页列表(基于 SearchInfo 优化表)
- GET /api/v1/movie/{mid}  影片详情(含多站点播放源聚合)
"""
from __future__ import annotations

import orjson
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as redis

from app.core.database import get_db, get_redis
from app.core.response import error_response, paging_response, success_response
from app.models.movie import MovieDetail
from app.models.search import SearchInfo
from app.models.slave_movie import SlaveMovieInfo

router = APIRouter(prefix="/api/v1", tags=["film"])

MASTER_CACHE_KEY = "film:cache:master"


def _slave_cache_key(source_id: str) -> str:
    return f"film:cache:slave:{source_id}"


@router.get("/movies")
async def list_movies(
    cid: int = Query(0, description="分类ID,0 表示全部"),
    current: int = Query(1, ge=1, description="当前页码"),
    pageSize: int = Query(20, ge=1, le=100, description="每页大小"),
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """分页获取影片列表。"""
    offset = (current - 1) * pageSize

    count_stmt = select(func.count(SearchInfo.mid))
    page_stmt = select(SearchInfo)

    if cid and cid > 0:
        count_stmt = count_stmt.where(SearchInfo.cid == cid)
        page_stmt = page_stmt.where(SearchInfo.cid == cid)

    total = (await db.execute(count_stmt)).scalar() or 0

    page_stmt = (
        page_stmt.order_by(SearchInfo.update_stamp.desc())
        .offset(offset)
        .limit(pageSize)
    )
    search_rows = (await db.execute(page_stmt)).scalars().all()
    mids = [row.mid for row in search_rows]

    if not mids:
        return paging_response([], total=0, current=current, page_size=pageSize)

    redis_map = await redis_client.hmget(MASTER_CACHE_KEY, *mids)
    movie_list: list[dict] = []
    missing_mids: list[str] = []

    for mid, raw in zip(mids, redis_map):
        if raw:
            movie = orjson.loads(raw)  # ⚠️ 修复 2: 只需一次反序列化
            movie_list.append(movie)
        else:
            missing_mids.append(mid)

    if missing_mids:
        stmt = select(MovieDetail).where(MovieDetail.mid.in_(missing_mids))
        rows = (await db.execute(stmt)).scalars().all()
        for row in rows:
            movie_list.append(_movie_to_dict(row))

    return paging_response(
        list_data=movie_list,
        total=total,
        current=current,
        page_size=pageSize,
    )


@router.get("/movie/{mid}")
async def movie_detail(
    mid: str,
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
):
    """影片详情 + 多站点播放源聚合。"""
    movie: dict | None = None

    raw = await redis_client.hget(MASTER_CACHE_KEY, mid)
    if raw:
        movie = orjson.loads(raw)  # ⚠️ 修复 2: 只需一次反序列化
    else:
        stmt = select(MovieDetail).where(MovieDetail.mid == mid)
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return error_response("影片不存在")
        movie = _movie_to_dict(row)

    play_from: list[str] = list(movie.get("play_from") or [])
    play_list: list[list[dict]] = list(movie.get("play_list") or [])

    # ⚠️ 修复 3: 彻底删除 Redis scan_iter 扫描从站缓存逻辑，改为直接查询数据库
    stmt = select(SlaveMovieInfo).where(SlaveMovieInfo.mid == mid)
    slave_rows = (await db.execute(stmt)).scalars().all()
    for slave in slave_rows:
        if slave.play_list:
            play_from.append(slave.sid)
            play_list.extend(slave.play_list)

    movie["play_from"] = play_from
    movie["play_list"] = play_list
    movie["mid"] = mid
    return success_response(movie)


def _movie_to_dict(row: MovieDetail) -> dict:
    """ORM 行转 dict"""
    return {
        "mid": row.mid,
        "cid": row.cid,
        "pid": row.pid,
        "vod_id": row.db_id,
        "vod_pic": row.picture,
        "vod_actor": row.actor,
        "vod_director": row.director,
        "vod_blurb": row.blurb,
        "vod_remarks": row.remarks,
        "vod_area": row.area,
        "vod_year": row.year,
        "play_from": row.play_from or [],
        "play_list": row.play_list or [],
    }
