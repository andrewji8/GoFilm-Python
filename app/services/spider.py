"""
核心爬虫与数据处理服务 (Spider Service)

本模块负责影视站点的数据采集、解析、归一化与缓存暂存,
对应原 Go 项目的 spider 核心逻辑。
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any
from xml.etree import ElementTree as ET

import httpx
import orjson
import redis.asyncio as redis

from app.core.config import SpiderSettings
from app.models.film_source import FilmSource

UTF8_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}


# ============================================================
# 1. 名称归一化与哈希
# ============================================================
_SEASON_PATTERN = re.compile(
    r"(season\s*\d+|[sS]\d+|第\s*\d+\s*季|剧场版|OVA|OAD|SP)",
    flags=re.IGNORECASE,
)
_ROMAN_MAP = {
    "Ⅰ": "1", "Ⅱ": "2", "Ⅲ": "3", "Ⅳ": "4",
    "Ⅴ": "5", "Ⅵ": "6", "Ⅶ": "7", "Ⅷ": "8",
    "Ⅸ": "9", "Ⅹ": "10",
}
_SPECIAL_CHARS = re.compile(r"[★☆♥♪♂♀①②③④⑤⑥⑦⑧⑨⑩]")
_WHITESPACE = re.compile(r"\s+")
_TRIM_PUNCT = re.compile(r"^[^\w\u4e00-\u9fff]+|[^\w\u4e00-\u9fff]+$")


def _normalize_name(name: str) -> str:
    """名称归一化: 去空格、统一季数写法、去首尾标点"""
    if not name:
        return ""
    normalized = name
    for roman, arabic in _ROMAN_MAP.items():
        normalized = normalized.replace(roman, arabic)
    normalized = _SPECIAL_CHARS.sub("", normalized)
    normalized = _SEASON_PATTERN.sub(lambda m: f"S{m.group(1)}" if m.group(1) else "", normalized)
    normalized = _WHITESPACE.sub("", normalized)
    normalized = _TRIM_PUNCT.sub("", normalized)
    return normalized


def generate_hash_key(name: str) -> str:
    """
    模拟原 Go 项目的 FNV-32a 哈希:
    1. 名称归一化
    2. 使用 hashlib.blake2b(digest_size=8) 生成 64 位无符号整数  # ⚠️ 修复 5: 升级为 64 位哈希
    3. 转十进制字符串返回,作为影片跨站点聚合的 mid
    """
    normalized = _normalize_name(name)
    digest = hashlib.blake2b(normalized.encode("utf-8"), digest_size=8).digest()  # ⚠️ 修复 5: 升级为 64 位哈希
    unsigned_64 = int.from_bytes(digest, byteorder="big", signed=False)  # ⚠️ 修复 5: 64 位无符号整数
    return str(unsigned_64)


# ============================================================
# 2. 播放地址解析
# ============================================================
def parse_play_url(play_url_str: str) -> list[list[dict[str, str]]]:
    """
    解析苹果CMS 的 vod_play_url 字段。

    单播放源格式:
        第01集$https://xxx.com/1.mp4#第02集$https://xxx.com/2.mp4

    多播放源格式:
        m3u8$第01集$link#...$$$yun$第01集$link#...

    返回二维列表: [[{episode, link}, {episode, link}, ...]]
    """
    if not play_url_str:
        return [[]]

    result: list[list[dict[str, str]]] = []
    sources = play_url_str.split("$$$")
    for source in sources:
        episodes: list[dict[str, str]] = []
        for item in source.split("#"):
            if "$" not in item:
                continue
            episode, link = item.split("$", 1)
            episode = episode.strip()
            link = link.strip()
            if episode and link:
                episodes.append({"episode": episode, "link": link})
        if episodes:
            result.append(episodes)
    return result or [[]]


def parse_play_from(play_from_str: str) -> list[str]:
    """解析 vod_play_from 字段(播放源名称),以 $$$ 分隔"""
    if not play_from_str:
        return []
    return [s.strip() for s in play_from_str.split("$$$") if s.strip()]


# ============================================================
# 3. XML / JSON 响应解析(苹果CMS标准接口)
# ============================================================
def parse_xml_response(content: bytes) -> list[dict[str, Any]]:
    """解析苹果CMS XML 格式的影片列表响应"""
    movies: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return movies

    # 标准结构: <rss><list><item>...</item></list></rss>
    for item in root.iter("item"):
        movie = {}
        for child in item:
            tag = child.tag.strip()
            text = (child.text or "").strip()
            movie[tag] = text
        if movie:
            movies.append(movie)
    return movies


def parse_json_response(content: bytes) -> list[dict[str, Any]]:
    """解析苹果CMS JSON 格式的影片列表响应"""
    try:
        data = orjson.loads(content)
    except orjson.JSONDecodeError:
        return []

    if isinstance(data, dict):
        for key in ("list", "data", "items"):
            if key in data and isinstance(data[key], list):
                return data[key]
        return [data]
    if isinstance(data, list):
        return data
    return []


# ============================================================
# 4. 异步 HTTP 请求(支持重试与指数退避)
# ============================================================
async def fetch_with_retry(
    url: str,
    params: dict[str, Any] | None = None,
    settings: SpiderSettings | None = None,
) -> bytes:
    """
    异步 HTTP GET 请求,失败自动重试。
    """
    cfg = settings or SpiderSettings()
    timeout = httpx.Timeout(cfg.timeout)
    params = params or {}

    last_exc: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                headers=UTF8_HEADERS,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return resp.content
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_exc = exc
            if attempt >= cfg.max_retries:
                break
            await asyncio.sleep(2 ** (attempt - 1))

    raise RuntimeError(
        f"fetch_with_retry failed after {cfg.max_retries} attempts: {url}"
    ) from last_exc


# ============================================================
# 5. 并发采集
# ============================================================
async def _fetch_one_page(
    source: FilmSource,
    page: int,
    hours: int,
    settings: SpiderSettings,
) -> list[dict[str, Any]]:
    """
    实际的 HTTP + 解析逻辑(纯函数,不含并发控制与休眠,
    并发控制与限速由上层 _task 闭包负责,
    避免 Semaphore 不可重入导致的死锁)。
    """
    params: dict[str, Any] = {"ac": "list", "pg": page}
    if hours > 0:
        params["h"] = hours

    content = await fetch_with_retry(source.uri, params=params, settings=settings)

    if b"<?xml" in content[:64] or b"<rss" in content[:64]:
        return parse_xml_response(content)
    return parse_json_response(content)


async def collect_page_concurrently(
    source: FilmSource,
    page: int,
    hours: int,
    settings: SpiderSettings,
) -> list[dict[str, Any]]:
    """并发采集某个采集源的单页数据。"""
    sem = asyncio.Semaphore(settings.concurrency)

    async def _task() -> list[dict[str, Any]]:
        await asyncio.sleep(settings.delay_ms / 1000.0)
        async with sem:
            return await _fetch_one_page(source, page, hours, settings)

    results = await asyncio.gather(_task(), return_exceptions=True)
    if isinstance(results[0], Exception):
        return []
    return results[0]


async def collect_pages_concurrently(
    source: FilmSource,
    pages: int,
    hours: int,
    settings: SpiderSettings,
) -> list[dict[str, Any]]:
    """并发采集某个采集源的多页数据。"""
    sem = asyncio.Semaphore(settings.concurrency)

    async def _task(p: int) -> list[dict[str, Any]]:
        await asyncio.sleep(settings.delay_ms / 1000.0)
        async with sem:
            return await _fetch_one_page(source, p, hours, settings)

    results = await asyncio.gather(
        *[_task(p) for p in range(1, pages + 1)],
        return_exceptions=True,
    )

    all_movies: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, Exception):
            continue
        all_movies.extend(item)
    return all_movies


# ============================================================
# 6. Redis 暂存
# ============================================================
MASTER_CACHE_KEY = "film:cache:master"


def _slave_cache_key(source_id: str) -> str:
    return f"film:cache:slave:{source_id}"


async def cache_to_redis(
    redis_client: redis.Redis,
    source_id: str,
    is_master: bool,
    movie_list: list[dict[str, Any]],
) -> int:
    """将采集结果暂存至 Redis Hash。"""
    if not movie_list:
        return 0

    key = MASTER_CACHE_KEY if is_master else _slave_cache_key(source_id)
    pipe = redis_client.pipeline(transaction=False)

    for movie in movie_list:
        name = movie.get("vod_name") or movie.get("title") or ""
        mid = movie.get("mid") or generate_hash_key(name)
        movie["mid"] = mid  # ⚠️ 修复 2: 将 mid 直接注入字典
        movie["db_id"] = movie.get("vod_id") or movie.get("id") or 0  # ⚠️ 修复 2: 将 db_id 直接注入字典
        pipe.hset(key, mid, orjson.dumps(movie).decode("utf-8"))  # ⚠️ 修复 2: 只序列化一层

    await pipe.execute()
    return len(movie_list)
