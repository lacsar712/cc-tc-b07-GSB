import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text

from claimer import start as start_claimer
from models import (
    DEFAULT_SEGMENT,
    SEGMENTS,
    Base,
    ConvergenceLog,
    MergeBatch,
    MergeItem,
    SessionLocal,
    engine,
    merge_dict,
    row_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    # 老库兜底：补 segment 列并回填默认部位（仅 Postgres 需要，新库 create_all 已带列）
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE convergence_logs ADD COLUMN IF NOT EXISTS segment VARCHAR")
            )
            conn.execute(
                text("UPDATE convergence_logs SET segment = :seg WHERE segment IS NULL"),
                {"seg": DEFAULT_SEGMENT},
            )
            conn.execute(
                text("ALTER TABLE convergence_logs ALTER COLUMN segment SET NOT NULL")
            )
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
            from rules import judge

            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    chainage=chainage,
                    segment=DEFAULT_SEGMENT,
                    delta_mm=delta,
                    status="done",
                    verdict=verdict,
                    reason=reason,
                    created_by="surveyor",
                    created_at=now,
                    processed_at=now,
                )
            )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "role": payload.get("role")}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn=None, message="仅测量员可提交收敛读数"):
    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"detail": "未登录"}), 401
            if user["role"] != "writer":
                return jsonify({"detail": message}), 403
            g.user = user
            return f(*args, **kwargs)

        return wrapper

    return deco(fn) if fn is not None else deco


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "role": user["role"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "role": user["role"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    segment = (body.get("segment") or DEFAULT_SEGMENT).strip() or DEFAULT_SEGMENT
    if segment not in SEGMENTS:
        return jsonify({"detail": "部位类别须为拱顶、边墙或注浆段"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        row = ConvergenceLog(
            chainage=chainage,
            segment=segment,
            delta_mm=delta_mm,
            status="pending",
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()


def fetch_merge_rows(db, log_ids):
    """校验勾选：至少两笔、全部存在、全部已办结、同一部位类别。

    返回 (rows, None) 或 (None, (response, status))。
    """
    if not isinstance(log_ids, list) or not log_ids:
        return None, (jsonify({"detail": "请勾选要合成的测缝单"}), 400)
    try:
        ids = [int(i) for i in log_ids]
    except (TypeError, ValueError):
        return None, (jsonify({"detail": "测缝单编号无效"}), 400)
    ids = list(dict.fromkeys(ids))
    if len(ids) < 2:
        return None, (jsonify({"detail": "至少勾选两笔同类已办结单才能合成"}), 400)
    rows = (
        db.query(ConvergenceLog)
        .filter(ConvergenceLog.id.in_(ids))
        .order_by(ConvergenceLog.id)
        .all()
    )
    if len(rows) != len(ids):
        return None, (jsonify({"detail": "所选测缝单不存在或已被移除"}), 400)
    if any(r.status != "done" for r in rows):
        return None, (jsonify({"detail": "只能合成已办结单，未办结单不能勾入"}), 400)
    if len({r.segment for r in rows}) > 1:
        return None, (
            jsonify({"detail": "拱顶、边墙、注浆段等不同类别不能混入同一笔合成"}),
            400,
        )
    return rows, None


def merge_average(rows) -> float:
    """后台统一算平均：来源毫米值之和除以笔数，不在前端心算。"""
    return sum(float(r.delta_mm) for r in rows) / len(rows)


def preview_payload(rows):
    return {
        "segment": rows[0].segment,
        "count": len(rows),
        "average_mm": merge_average(rows),
        "sources": [row_dict(r) for r in rows],
    }


@app.post("/api/merges/preview")
@require_login
def preview_merge():
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        rows, err = fetch_merge_rows(db, body.get("log_ids"))
        if err:
            return err
        return jsonify(preview_payload(rows))
    finally:
        db.close()


@app.get("/api/merges/preview")
@require_login
def preview_merge_get():
    raw = request.args.get("ids", "")
    try:
        log_ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        return jsonify({"detail": "测缝单编号无效"}), 400
    db = SessionLocal()
    try:
        rows, err = fetch_merge_rows(db, log_ids)
        if err:
            return err
        return jsonify(preview_payload(rows))
    finally:
        db.close()


@app.post("/api/merges")
@require_writer(message="仅测量员可生成合成单，巡检员仅可预览")
def create_merge():
    body = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        rows, err = fetch_merge_rows(db, body.get("log_ids"))
        if err:
            return err
        segment = rows[0].segment
        average = merge_average(rows)
        now = datetime.now(timezone.utc)
        chainage = "合成:" + "、".join(r.chainage for r in rows)
        # 新单进待认领，由认领线程后续判定，绝不直接写成已办结
        new_log = ConvergenceLog(
            chainage=chainage,
            segment=segment,
            delta_mm=average,
            status="pending",
            created_by=g.user["username"],
            created_at=now,
        )
        db.add(new_log)
        db.flush()
        # 合成流水与生成结果同一事务落库，缺一边整体回滚
        batch = MergeBatch(
            segment=segment,
            average_mm=average,
            result_log_id=new_log.id,
            created_by=g.user["username"],
            created_at=now,
        )
        db.add(batch)
        db.flush()
        db.add_all([MergeItem(batch_id=batch.id, log_id=r.id) for r in rows])
        payload = {
            "batch": {
                "id": batch.id,
                "segment": segment,
                "average_mm": average,
                "result_log_id": new_log.id,
                "source_log_ids": [r.id for r in rows],
                "created_by": g.user["username"],
                "created_at": now.isoformat(),
            },
            "log": row_dict(new_log),
        }
        db.commit()
        return jsonify(payload), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/merges")
@require_login
def list_merges():
    db = SessionLocal()
    try:
        batches = db.query(MergeBatch).order_by(MergeBatch.id.desc()).all()
        return jsonify([merge_dict(b) for b in batches])
    finally:
        db.close()
