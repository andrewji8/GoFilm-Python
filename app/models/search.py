"""
SearchInfo: 检索优化表
影片的精简冗余表,仅保留搜索/分页/排序所需的字段,
用于减轻主表查询压力,与原 Go 项目 SearchInfo 对齐。
"""
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SearchInfo(Base):
    """检索优化表"""

    __tablename__ = "search_info"

    mid: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        comment="归一化哈希ID (与 MovieDetail.mid 对齐)",
    )
    cid: Mapped[int] = mapped_column(
        Integer,
        index=True,
        default=0,
        comment="一级分类ID(冗余)",
    )
    pid: Mapped[int] = mapped_column(
        Integer,
        index=True,
        default=0,
        comment="二级分类ID(冗余)",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        index=True,
        nullable=False,
        comment="影片名称(冗余)",
    )
    class_tag: Mapped[str] = mapped_column(
        String(128),
        default="",
        comment="分类展示标签(如 '动作·2024')",
    )
    year: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="年份(冗余)",
    )
    update_stamp: Mapped[int] = mapped_column(
        Integer,
        index=True,
        default=0,
        comment="更新时间戳(秒级),用于排序",
    )

    __table_args__ = (
        Index("idx_search_cid_update", "cid", "update_stamp"),
        Index("idx_search_pid_update", "pid", "update_stamp"),
    )

    def __repr__(self) -> str:
        return f"<SearchInfo mid={self.mid} name={self.name}>"
