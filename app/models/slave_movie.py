"""
SlaveMovieInfo: 附属站点播放源表
存储非主站采集源中与主站影片 mid 关联的额外播放地址,
用于详情页多站点聚合播放,与原 Go 项目 SlaveMovieInfo 对齐。
"""
from sqlalchemy import JSON, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SlaveMovieInfo(Base):
    """附属站点播放源表"""

    __tablename__ = "slave_movie_info"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment="自增主键",
    )
    sid: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
        comment="采集站ID(关联 film_source.id)",
    )
    mid: Mapped[str] = mapped_column(
        String(32),
        index=True,
        nullable=False,
        comment="关联主站影片ID (归一化哈希)",
    )
    db_id: Mapped[int] = mapped_column(
        Integer,
        index=True,
        default=0,
        comment="从站原始影片ID",
    )
    play_list: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="从站播放地址二维列表 (List[List[Dict[str,str]]])",
    )

    __table_args__ = (
        UniqueConstraint("sid", "mid", name="uq_slave_sid_mid"),  # ⚠️ 性能重构: 添加联合唯一约束，支持原生批量 Upsert
        Index("idx_slave_sid_mid", "sid", "mid"),
        Index("idx_slave_sid_dbid", "sid", "db_id"),
    )

    def __repr__(self) -> str:
        return f"<SlaveMovieInfo sid={self.sid} mid={self.mid}>"
