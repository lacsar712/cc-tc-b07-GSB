import os
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# 测缝部位类别：拱顶与边墙不得混勾进同一笔合成，注浆段单列。
MEASURE_TYPES = ("拱顶", "边墙", "注浆段")
DEFAULT_MEASURE_TYPE = "拱顶"


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    measure_type: Mapped[str] = mapped_column(String, nullable=False, default=DEFAULT_MEASURE_TYPE)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MergeFlow(Base):
    """合成流水：每生成一笔合成新单就同时落一条，缺一边都不记账。"""

    __tablename__ = "merge_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    result_log_id: Mapped[int] = mapped_column(
        ForeignKey("convergence_logs.id"), nullable=False
    )
    measure_type: Mapped[str] = mapped_column(String, nullable=False)
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    average_mm: Mapped[float] = mapped_column(Float, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    result: Mapped[ConvergenceLog] = relationship()


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "measure_type": row.measure_type,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def flow_dict(flow: MergeFlow) -> dict:
    return {
        "id": flow.id,
        "result_log_id": flow.result_log_id,
        "measure_type": flow.measure_type,
        "source_ids": flow.source_ids,
        "average_mm": flow.average_mm,
        "created_by": flow.created_by,
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "result": row_dict(flow.result) if flow.result else None,
    }
