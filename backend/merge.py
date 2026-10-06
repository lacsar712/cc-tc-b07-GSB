"""已办结测缝合成：至少两笔同类已办结，平均毫米由后台算出，前端不心算。"""
from models import MEASURE_TYPES, ConvergenceLog

MIN_SOURCES = 2


def parse_ids(raw) -> tuple[list[int] | None, str | None]:
    """从请求体取出去重后的编号列表；非法时给出拒收原因。"""
    if not isinstance(raw, list):
        return None, "勾选编号必须是列表"
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in raw):
        return None, "勾选编号必须全是整数"
    ids = list(dict.fromkeys(raw))
    return ids, None


def gather(db, ids: list[int]) -> tuple[list[ConvergenceLog] | None, str | None]:
    """按勾选顺序取单并做硬校验：够两笔、全已办结、全同类，缺一拒收。"""
    if len(ids) < MIN_SOURCES:
        return None, f"至少勾选 {MIN_SOURCES} 笔已办结测缝才能合成"

    rows_by_id = {
        row.id: row
        for row in db.query(ConvergenceLog).filter(ConvergenceLog.id.in_(ids)).all()
    }
    missing = [i for i in ids if i not in rows_by_id]
    if missing:
        return None, f"勾选的编号不存在：{', '.join(map(str, missing))}"

    rows = [rows_by_id[i] for i in ids]

    not_done = [r.id for r in rows if r.status != "done"]
    if not_done:
        return None, f"只允许合成已办结测缝，以下仍未办结：{', '.join(map(str, not_done))}"

    types_ = {r.measure_type for r in rows}
    if len(types_) > 1:
        return None, f"不能混勾类别（{'、'.join(sorted(types_))}），同一笔合成只能取同类测缝"

    measure_type = rows[0].measure_type
    if measure_type not in MEASURE_TYPES:
        return None, f"未知测缝类别：{measure_type}"

    return rows, None


def average_mm(rows: list[ConvergenceLog]) -> float:
    # 平均值只在后台算；保留 3 位小数，避免浮点二进制尾差导致前后端看似不一致。
    return round(sum(float(r.delta_mm) for r in rows) / len(rows), 3)
