"""
统一 API 响应格式封装

所有 API 接口必须返回以下结构:
   成功: {"code": 0, "msg": "success", "data": ...}
   失败: {"code": -1, "msg": "xxx",      "data": None}
   分页: {"code": 0,  "msg": "success", "data": {"list": [...], "paging": {...}}}
"""
from __future__ import annotations

import math
from typing import Any


def success_response(data: Any = None, msg: str = "success") -> dict:
    """成功响应"""
    return {"code": 0, "msg": msg, "data": data}


def error_response(msg: str, code: int = -1, data: Any = None) -> dict:
    """失败响应"""
    return {"code": code, "msg": msg, "data": data}


def paging_response(
    list_data: list,
    total: int,
    current: int,
    page_size: int,
    msg: str = "success",
) -> dict:
    """
    分页响应包装:
    {
        "code": 0,
        "msg": "success",
        "data": {
            "list": [...],
            "paging": {
                "pageSize":  int,
                "current":   int,
                "pageCount": int,
                "total":     int
            }
        }
    }
    """
    if page_size <= 0:
        page_size = 1
    page_count = math.ceil(total / page_size) if total > 0 else 0
    data = {
        "list": list_data,
        "paging": {
            "pageSize": page_size,
            "current": current,
            "pageCount": page_count,
            "total": total,
        },
    }
    return success_response(data=data, msg=msg)
