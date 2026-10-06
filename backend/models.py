import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# 测缝部位类别：拱顶、边墙、注浆段。不同类别不能混入同一笔合成。
SEGMENTS = ("拱顶", "边墙", "注浆段")
DEFAULT_SEGMENT = "拱顶"


class Base(DeclarativeBase):
    pass


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    segment: Mapped[str] = mapped_column(String, nullable=False, default=DEFAULT_SEGMENT)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MergeBatch(Base):
    """合成流水：一笔合成一条，与生成的新单同事务落库。"""

    __tablename__ = "merge_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    segment: Mapped[str] = mapped_column(String, nullable=False)
    average_mm: Mapped[float] = mapped_column(Float, nullable=False)
    result_log_id: Mapped[int] = mapped_column(
        ForeignKey("convergence_logs.id"), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    items: Mapped[list["MergeItem"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )
    result_log: Mapped[ConvergenceLog] = relationship()


class MergeItem(Base):
    """合成流水明细：一笔合成勾选的来源测缝单。"""

    __tablename__ = "merge_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("merge_batches.id"), nullable=False)
    log_id: Mapped[int] = mapped_column(ForeignKey("convergence_logs.id"), nullable=False)

    batch: Mapped[MergeBatch] = relationship(back_populates="items")
    log: Mapped[ConvergenceLog] = relationship()


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "segment": row.segment,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }


def merge_dict(batch: MergeBatch) -> dict:
    return {
        "id": batch.id,
        "segment": batch.segment,
        "average_mm": batch.average_mm,
        "result_log_id": batch.result_log_id,
        "source_log_ids": [item.log_id for item in batch.items],
        "created_by": batch.created_by,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }
