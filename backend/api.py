import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import inspect, text

from claimer import start as start_claimer
from merge import average_mm, gather, parse_ids
from models import (
    MEASURE_TYPES,
    Base,
    ConvergenceLog,
    MergeFlow,
    SessionLocal,
    engine,
    flow_dict,
    row_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
USERS = {
    "surveyor": {"role": "writer", "password_hash": pwd.hash("surv123456")},
    "inspector": {"role": "reader", "password_hash": pwd.hash("insp123456")},
}

app = Flask(__name__)


def ensure_columns():
    """旧库补列：create_all 不会给已存在的表加 measure_type。"""
    insp = inspect(engine)
    if "convergence_logs" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("convergence_logs")}
    if "measure_type" not in cols:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE convergence_logs "
                    "ADD COLUMN measure_type VARCHAR NOT NULL DEFAULT '拱顶'"
                )
            )


def seed():
    Base.metadata.create_all(engine)
    ensure_columns()
    db = SessionLocal()
    try:
        if db.query(ConvergenceLog).count() > 0:
            return
        now = datetime.now(timezone.utc)
        # 拱顶两笔合格可立即合成；边墙、注浆段各一笔，单独不够两笔只能拒收。
        for chainage, measure_type, delta, expect in (
            ("K12+180", "拱顶", 1.2, "合格"),
            ("K12+220", "拱顶", 2.0, "合格"),
            ("K18+040", "拱顶", 5.6, "超限"),
            ("K18+060", "边墙", 4.2, "超限"),
            ("K22+100", "注浆段", 0.8, "合格"),
        ):
            from rules import judge

            verdict, reason = judge(delta)
            assert verdict == expect
            db.add(
                ConvergenceLog(
                    measure_type=measure_type,
                    chainage=chainage,
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


def require_writer(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "仅测量员可写测缝数据"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


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
    measure_type = (body.get("measure_type") or "").strip()
    if measure_type not in MEASURE_TYPES:
        return jsonify({"detail": f"类别必须是：{'、'.join(MEASURE_TYPES)}"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        row = ConvergenceLog(
            measure_type=measure_type,
            chainage=chainage,
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


def read_merge_ids():
    body = request.get_json(silent=True) or {}
    ids, err = parse_ids(body.get("ids"))
    if err is not None:
        return None, None, (jsonify({"detail": err}), 400)
    db = SessionLocal()
    rows, err = gather(db, ids)
    if err is not None:
        db.close()
        return None, None, (jsonify({"detail": err}), 400)
    return db, (ids, rows), None


@app.post("/api/merge/preview")
@require_login
def merge_preview():
    """巡检员也能看预览；平均毫米只在这里（后台）算，前端只展示。"""
    db, picked, error = read_merge_ids()
    if error is not None:
        return error
    try:
        ids, rows = picked
        avg = average_mm(rows)
        return jsonify(
            {
                "ids": ids,
                "count": len(rows),
                "measure_type": rows[0].measure_type,
                "average_mm": avg,
                "sources": [row_dict(r) for r in rows],
            }
        )
    finally:
        db.close()


@app.post("/api/merge")
@require_writer
def merge_create():
    """生成新待认领单与合成流水必须同一事务一起落库，缺一边回滚。"""
    db, picked, error = read_merge_ids()
    if error is not None:
        return error
    try:
        ids, rows = picked
        measure_type = rows[0].measure_type
        avg = average_mm(rows)
        now = datetime.now(timezone.utc)
        chainage = f"合成({measure_type})#" + "+".join(str(i) for i in ids)
        new_row = ConvergenceLog(
            measure_type=measure_type,
            chainage=chainage,
            delta_mm=avg,
            status="pending",
            created_by=g.user["username"],
            created_at=now,
        )
        db.add(new_row)
        db.flush()  # 取 new_row.id，流水外键才能挂上
        flow = MergeFlow(
            result_log_id=new_row.id,
            measure_type=measure_type,
            source_ids=ids,
            average_mm=avg,
            created_by=g.user["username"],
            created_at=now,
        )
        db.add(flow)
        db.commit()
        db.refresh(new_row)
        db.refresh(flow)
        return jsonify({"log": row_dict(new_row), "flow": flow_dict(flow)}), 201
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/merge/flows")
@require_login
def merge_flows():
    db = SessionLocal()
    try:
        flows = db.query(MergeFlow).order_by(MergeFlow.id.desc()).all()
        return jsonify([flow_dict(f) for f in flows])
    finally:
        db.close()
