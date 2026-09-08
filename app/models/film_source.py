"""
FilmSource: 采集源配置表
存储外部影视站点的接口地址及采集策略,与原 Go 项目 FilmSource 对齐。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FilmSource(Base):
    """采集源配置"""

    __tablename__ = "film_source"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        comment="采集源唯一标识 (如 'source_01')",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="采集源显示名称",
    )
    uri: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="采集接口地址(支持苹果CMS标准接口)",
    )
    is_master: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否为主站(主站数据写入 MovieDetail,从站仅写入 SlaveMovieInfo)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用该采集源",
    )
    interval_ms: Mapped[int] = mapped_column(
        Integer,
        default=500,
        nullable=False,
        comment="请求间隔(毫秒),用于限速",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )

    def __repr__(self) -> str:
        return f"<FilmSource id={self.id} name={self.name}>"
