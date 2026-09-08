"""
定时任务与 Redis -> MySQL 同步服务

本模块负责:
1. sync_redis_to_mysql  使用 HSCAN 游标将 Redis 采集缓存批量 Upsert 到 MySQL
2. start_scheduler       初始化 APScheduler 定时任务
3. _scheduled_collect    后台增量采集(每日凌晨 3 点)
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone  # ⚠️ 修复 4: 导入 timezone

import orjson
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.dialects.mysql import insert as mysql_insert

import redis.asyncio as redis

from app.core.config import settings
from app.core.database import AsyncSessionLocal, redis_client
from app.models.film_source import FilmSource
from app.models.movie import MovieDetail
from app.models.search import SearchInfo
from app.models.slave_movie import SlaveMovieInfo
from app.services.spider import (
    cache_to_redis,
    collect_pages_concurrently,
    generate_hash_key,
)

logger = logging.getLogger(__name__)

# HSCAN 每批大小(防止单批过大)
SCAN_BATCH = 500
MASTER_CACHE_KEY = "film:cache:master"


# ============================================================
# 1. 字段映射工具
# ============================================================
def _raw_to_movie_dict(payload: dict) -> dict:
    """
    将 Redis 中反序列化得到的 movie 字典
    转换为 MovieDetail 字段映射。  # ⚠️ 修复 2: 单层序列化后 payload 即为完整 movie 字典
    """
    data = payload
    name = data.get("vod_name") or data.get("title") or ""
    return {
        "mid": data["mid"],
        "cid": int(data.get("type_id") or data.get("cid") or 0),
        "pid": int(data.get("type_id_1") or data.get("pid") or 0),
        "name": name,
        "picture": data.get("vod_pic") or "",
        "actor": data.get("vod_actor") or "",
        "director": data.get("vod_director") or "",
        "blurb": data.get("vod_blurb") or "",
        "remarks": data.get("vod_remarks") or "",
        "area": data.get("vod_area") or "",
        "year": str(data.get("vod_year") or ""),
        "play_from": data.get("vod_play_from_list") or (
            data.get("vod_play_from", "").split("$$$")
            if data.get("vod_play_from") else []
        ),
        "play_list": data.get("vod_play_url_list") or [],
        "db_id": int(data.get("db_id") or 0),
    }


# ============================================================
# 2. Upsert 核心（原生批量 Upsert，无 SELECT 竞态）
# ============================================================
async def _upsert_movie_batch(db, items: list[dict]) -> None:  # ⚠️ 性能重构: 删除 SELECT 查询和逐条 UPDATE
    """主站 MovieDetail 批量 Upsert（一步到位，无竞态）。"""
    if not items:
        return

    # ⚠️ 性能重构: 直接使用 mysql_insert().on_duplicate_key_update() 进行批量 Upsert，无需先 SELECT 判断存在性
    stmt_ins = mysql_insert(MovieDetail).values(items)
    stmt_ins = stmt_ins.on_duplicate_key_update(
        play_from=stmt_ins.inserted.play_from,
        play_list=stmt_ins.inserted.play_list,
        remarks=stmt_ins.inserted.remarks,
        update_time=datetime.now(timezone.utc),  # ⚠️ 修复 4: 使用 timezone-aware 的 UTC 时间
    )
    await db.execute(stmt_ins)

    now_stamp = int(time.time())
    search_rows = [
        {
            "mid": it["mid"],
            "cid": it["cid"],
            "pid": it["pid"],
            "name": it["name"],
            "class_tag": f"{(it.get('area') or '')}·{(it.get('year') or '')}",
            "year": int(it["year"]) if (it["year"] or "").isdigit() else 0,
            "update_stamp": now_stamp,
        }
        for it in items
    ]
    if search_rows:
        stmt_search = mysql_insert(SearchInfo).values(search_rows)
        stmt_search = stmt_search.on_duplicate_key_update(
            cid=stmt_search.inserted.cid,
            pid=stmt_search.inserted.pid,
            name=stmt_search.inserted.name,
            class_tag=stmt_search.inserted.class_tag,
            year=stmt_search.inserted.year,
            update_stamp=stmt_search.inserted.update_stamp,
        )
        await db.execute(stmt_search)


async def _upsert_slave_batch(db, source_id: str, items: list[dict]) -> None:  # ⚠️ 性能重构: 删除 SELECT 查询和逐条 UPDATE
    """从站 SlaveMovieInfo 批量 Upsert（一步到位，无竞态）。"""
    if not items:
        return

    slave_items = [
        {
            "sid": source_id,
            "mid": it["mid"],
            "db_id": int(it.get("db_id") or 0),
            "play_list": it["play_list"],
        }
        for it in items
    ]

    # ⚠️ 性能重构: 直接使用 mysql_insert().on_duplicate_key_update() 进行批量 Upsert，无需先 SELECT 判断存在性
    stmt_ins = mysql_insert(SlaveMovieInfo).values(slave_items)
    stmt_ins = stmt_ins.on_duplicate_key_update(
        play_list=stmt_ins.inserted.play_list,
        db_id=stmt_ins.inserted.db_id,
    )
    await db.execute(stmt_ins)


# ============================================================
# 3. HSCAN 同步主循环
# ============================================================
async def _scan_and_sync_key(
    db,
    redis_client: redis.Redis,
    key: str,
    is_master: bool,
    source_id: str | None = None,
) -> int:
    """
    单个 Redis Hash 键的同步循环:
    - HSCAN 游标分批拉取(避免 OOM)
    - 累积到 SCAN_BATCH 后一次性 Upsert
    - 成功后 HDEL 该批 field
    """
    synced = 0
    cursor = 0
    pipe = redis_client.pipeline(transaction=False)

    while True:
        cursor, fields = await redis_client.hscan(key, cursor=cursor, count=SCAN_BATCH)
        if not fields:
            if cursor == 0:
                break
            continue

        batch_items: list[dict] = []
        batch_fields: list[str] = []

        for field, raw in fields.items():
            try:
                payload = orjson.loads(raw)
            except Exception as exc:
                logger.warning("解析 Redis 缓存失败 key=%s field=%s err=%s", key, field, exc)
                continue

            try:
                movie = _raw_to_movie_dict(payload)
                if not movie["name"]:
                    continue
                if not movie["mid"]:
                    movie["mid"] = generate_hash_key(movie["name"])
                batch_items.append(movie)
                batch_fields.append(field)
            except Exception as exc:
                logger.warning("字段映射失败 field=%s err=%s", field, exc)

        if not batch_items:
            if cursor == 0:
                break
            continue

        try:
            if is_master:
                await _upsert_movie_batch(db, batch_items)
            else:
                await _upsert_slave_batch(db, source_id or "", batch_items)
            await db.commit()
            pipe.hdel(key, *batch_fields)
            await pipe.execute()
            synced += len(batch_items)
            logger.info(
                "同步批次完成 key=%s is_master=%s count=%d cursor=%d",
                key, is_master, len(batch_items), cursor,
            )
        except Exception as exc:
            await db.rollback()
            logger.exception("批次同步失败 key=%s err=%s", key, exc)

        if cursor == 0:
            break

    return synced


async def sync_redis_to_mysql() -> dict:
    """同步入口: 主站 + 所有从站。"""
    result = {"master": 0, "slaves": {}}

    async with AsyncSessionLocal() as db:
        try:
            result["master"] = await _scan_and_sync_key(
                db, redis_client, MASTER_CACHE_KEY, is_master=True,
            )
        except Exception as exc:
            logger.exception("主站同步异常 err=%s", exc)

        async for slave_key in redis_client.scan_iter(match="film:cache:slave:*"):
            source_id = slave_key.split(":", 3)[-1]
            try:
                count = await _scan_and_sync_key(
                    db, redis_client, slave_key,
                    is_master=False, source_id=source_id,
                )
                result["slaves"][source_id] = count
            except Exception as exc:
                logger.exception("从站同步异常 sid=%s err=%s", source_id, exc)

    logger.info("Redis -> MySQL 同步完成 result=%s", result)
    return result


# ============================================================
# 4. 定时任务
# ============================================================
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _scheduled_full_sync() -> None:
    """全量同步任务(每周日凌晨 4 点)"""
    logger.info("开始执行全量同步任务")
    try:
        await sync_redis_to_mysql()
    except Exception as exc:
        logger.exception("全量同步任务失败 err=%s", exc)


async def _scheduled_collect() -> None:
    """每日增量采集任务(凌晨 3 点)"""
    logger.info("开始执行每日增量采集")
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(FilmSource).where(FilmSource.is_active.is_(True))
            sources = (await db.execute(stmt)).scalars().all()

        for src in sources:
            try:
                movies = await collect_pages_concurrently(
                    source=src,
                    pages=3,
                    hours=24,
                    settings=settings.spider,
                )
                for m in movies:
                    name = m.get("vod_name") or m.get("title") or ""
                    m["mid"] = generate_hash_key(name)
                await cache_to_redis(
                    redis_client=redis_client,
                    source_id=src.id,
                    is_master=src.is_master,
                    movie_list=movies,
                )
                logger.info("增量采集完成 sid=%s count=%d", src.id, len(movies))
                await asyncio.sleep(settings.spider.delay_ms / 1000.0)
            except Exception as exc:
                logger.exception("增量采集失败 sid=%s err=%s", src.id, exc)
    except Exception as exc:
        logger.exception("每日采集任务异常 err=%s", exc)


def start_scheduler() -> None:
    """启动 APScheduler,注册全部定时任务"""
    scheduler.add_job(
        _scheduled_full_sync,
        CronTrigger(day_of_week="sun", hour=4, minute=0),
        id="full_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _scheduled_collect,
        CronTrigger(hour=3, minute=0),
        id="daily_collect",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("APScheduler 已启动,定时任务已注册")
