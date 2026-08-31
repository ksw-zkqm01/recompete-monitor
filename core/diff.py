# -*- coding: utf-8 -*-
"""필드 단위 diff 엔진 — 어제 스냅샷과 오늘 스냅샷을 비교한다."""
from . import db
from .rules import EVENT, rule_for

IGNORE = {"entity_id", "_raw", "fetched_at", "source", "kind"}


def _norm(v):
    if v is None:
        return ""
    return str(v).strip()


def diff_day(con, source, kind, today=None, prev=None):
    """today/prev 를 지정하지 않으면 최근 두 스냅샷 일자를 자동으로 쓴다.
    반환: (rows_for_db, summary_dict)"""
    days = db.snapshot_days(con, source, kind)
    if not days:
        return [], {"error": "스냅샷이 없습니다"}
    today = today or days[0]
    if prev is None:
        earlier = [d for d in days if d < today]
        prev = earlier[0] if earlier else None

    cur = db.load_day(con, source, kind, today)
    if prev is None:
        # 최초 실행: 전부 NEW 로 기록하지 않는다(노이즈). 기준선만 잡는다.
        return [], {"baseline": True, "day": today, "records": len(cur),
                    "note": "최초 스냅샷 — 기준선만 저장했습니다. 내일부터 변화가 잡힙니다."}

    old = db.load_day(con, source, kind, prev)
    rows = []
    n_new = n_gone = n_chg = 0

    for eid, (payload, h) in cur.items():
        if eid not in old:
            sev, _, _ = EVENT[source]["NEW"]
            rows.append((source, kind, eid, today, "NEW", "*", None,
                         _norm(payload.get("title")), sev, prev))
            n_new += 1
            continue
        oldp, oldh = old[eid]
        if oldh == h:
            continue
        for k in sorted(set(payload) | set(oldp)):
            if k in IGNORE:
                continue
            a, b = _norm(oldp.get(k)), _norm(payload.get(k))
            if a == b:
                continue
            r = rule_for(source, k)
            sev = r[0] if r else "low"
            rows.append((source, kind, eid, today, "CHANGED", k, a, b, sev, prev))
            n_chg += 1

    for eid, (payload, h) in old.items():
        if eid not in cur:
            sev, _, _ = EVENT[source]["GONE"]
            rows.append((source, kind, eid, today, "GONE", "*",
                         _norm(payload.get("title")), None, sev, prev))
            n_gone += 1

    return rows, {"day": today, "prev": prev, "new": n_new,
                  "changed_fields": n_chg, "gone": n_gone,
                  "records_today": len(cur), "records_prev": len(old)}
