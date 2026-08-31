"""국가 무관 스냅샷/변화 저장소.

핵심 아이디어(미국 프로젝트 피벗에서 가져옴):
  '지금 무엇이 있는가'가 아니라 '어제와 무엇이 달라졌는가'를 판다.
  그래서 원본 레코드를 매일 스냅샷으로 남기고, 어제와 필드 단위로 비교한다.
"""
import hashlib
import json
import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "platform.sqlite3"

SCHEMA = """
-- 원본 레코드의 일자별 스냅샷. 같은 날 같은 레코드는 1행.
CREATE TABLE IF NOT EXISTS snapshot (
    source     TEXT NOT NULL,      -- kr | us
    kind       TEXT NOT NULL,      -- opportunity | contract | forecast
    entity_id  TEXT NOT NULL,
    taken_on   TEXT NOT NULL,      -- YYYYMMDD
    body_hash  TEXT NOT NULL,
    payload    TEXT NOT NULL,      -- 정규화된 레코드 JSON
    PRIMARY KEY (source, kind, entity_id, taken_on)
);
CREATE INDEX IF NOT EXISTS idx_snap_day ON snapshot(source, kind, taken_on);

-- 필드 단위 변화. 브리프의 원재료.
CREATE TABLE IF NOT EXISTS change (
    source      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    detected_on TEXT NOT NULL,
    event       TEXT NOT NULL,     -- NEW | CHANGED | GONE
    field       TEXT NOT NULL,     -- event=NEW/GONE 이면 '*'
    old_value   TEXT,
    new_value   TEXT,
    severity    TEXT NOT NULL,     -- high | medium | low
    prev_on     TEXT,              -- 비교 대상 스냅샷 일자
    PRIMARY KEY (source, kind, entity_id, detected_on, field)
);
CREATE INDEX IF NOT EXISTS idx_chg_day ON change(source, detected_on, severity);

-- 발송 로그(중복 발송 방지)
CREATE TABLE IF NOT EXISTS brief_log (
    customer_id TEXT NOT NULL,
    source      TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    detected_on TEXT NOT NULL,
    sent_at     TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (customer_id, source, entity_id, detected_on)
);
"""


def connect(path=None):
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def ymd(d=None):
    return (d or date.today()).strftime("%Y%m%d")


def body_hash(payload: dict) -> str:
    core = {k: v for k, v in payload.items() if not k.startswith("_")}
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def save_snapshot(con, source, kind, records, taken_on=None):
    """records: [{entity_id, ...정규화 필드...}]"""
    day = taken_on or ymd()
    rows = []
    for r in records:
        eid = str(r.get("entity_id") or "").strip()
        if not eid:
            continue
        rows.append((source, kind, eid, day, body_hash(r),
                     json.dumps(r, ensure_ascii=False, sort_keys=True)))
    con.executemany("INSERT OR REPLACE INTO snapshot VALUES (?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def snapshot_days(con, source, kind):
    return [r["taken_on"] for r in con.execute(
        "SELECT DISTINCT taken_on FROM snapshot WHERE source=? AND kind=? "
        "ORDER BY taken_on DESC", (source, kind))]


def load_day(con, source, kind, day):
    out = {}
    for r in con.execute(
            "SELECT entity_id, payload, body_hash FROM snapshot "
            "WHERE source=? AND kind=? AND taken_on=?", (source, kind, day)):
        out[r["entity_id"]] = (json.loads(r["payload"]), r["body_hash"])
    return out


def save_changes(con, rows):
    con.executemany("INSERT OR REPLACE INTO change VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    con.commit()
    return len(rows)


def changes_on(con, source, day, min_severity="low"):
    order = {"high": 3, "medium": 2, "low": 1}
    floor = order.get(min_severity, 1)
    rows = [dict(r) for r in con.execute(
        "SELECT * FROM change WHERE source=? AND detected_on=?", (source, day))]
    rows = [r for r in rows if order.get(r["severity"], 0) >= floor]
    grouped = {}
    for r in rows:
        grouped.setdefault(r["entity_id"], []).append(r)
    return grouped
