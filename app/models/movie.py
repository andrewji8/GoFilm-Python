"""
MovieDetail: 影片核心信息表
存储主站采集影片的全部元数据及播放源,与原 Go 项目 MovieDetail 对齐。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MovieDetail(Base):
    """影片核心信息表"""

    __tablename__ = "movie_detail"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    mid: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False,
        comment="归一化哈希ID (FNV-32a),用于跨站点聚合",
    )
    cid: Mapped[int] = mapped_column(
        Integer,
        index=True,
        default=0,
        comment="一级分类ID",
    )
    pid: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="二级分类ID",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
        comment="影片名称",
    )
    picture: Mapped[str] = mapped_column(
        String(512),
        default="",
        comment="海报图片URL",
    )
    actor: Mapped[str] = mapped_column(
        String(512),
        default="",
        comment="主演",
    )
    director: Mapped[str] = mapped_column(
        String(255),
        default="",
        comment="导演",
    )
    blurb: Mapped[str] = mapped_column(
        Text,
        default="",
        comment="剧情简介",
    )
    remarks: Mapped[str] = mapped_column(
        String(128),
        default="",
        comment="更新状态/集数备注(如 '更新至12集'/'HD')",
    )
    area: Mapped[str] = mapped_column(
        String(64),
        default="",
        comment="地区",
    )
    year: Mapped[str] = mapped_column(
        String(16),
        default="",
        comment="年份",
    )
    play_from: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="播放源名称列表 (如 ['m3u8','yun'])",
    )
    play_list: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="播放地址二维列表 (List[List[Dict[str,str]]])",
    )
    db_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        default=0,
        comment="采集源对应的原始站点影片ID(用于溯源)",
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    __table_args__ = (
        Index("idx_movie_cid_update", "cid", "update_time"),
    )

    def __repr__(self) -> str:
        return f"<MovieDetail id={self.id} mid={self.mid} name={self.name}>"
