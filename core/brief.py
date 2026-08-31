# -*- coding: utf-8 -*-
"""변화 → 액션 브리프. 문장은 rules.py의 사전 정의 템플릿에서만 나온다."""
import json
from datetime import date

from . import db
from .rules import EVENT, SEVERITY_LABEL, SEVERITY_POINTS, rule_for

ORDER = {"high": 3, "medium": 2, "low": 1}
DATE_FIELDS = {"bid_clse_date", "openg_date", "presnatn_date", "qlfct_rgst_clse_date",
               "period_end", "key_date", "end_date", "concl_date"}
MONEY_FIELDS = {"asign_bdgt_amt", "presmpt_prce", "amount"}


def fmt(field, v):
    v = (v or "").strip()
    if not v:
        return "(없음)"
    if field in DATE_FIELDS and v.isdigit() and len(v) == 8:
        return f"{v[:4]}-{v[4:6]}-{v[6:]}"
    if field in MONEY_FIELDS and v.replace("-", "").isdigit():
        n = int(v)
        return f"{n/100_000_000:.2f}억원".rstrip("0").rstrip(".") + "" if n >= 100_000_000 else f"{n:,}원"
    return v
MARK = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}


def _latest_payload(con, source, kind, eid):
    r = con.execute(
        "SELECT payload FROM snapshot WHERE source=? AND kind=? AND entity_id=? "
        "ORDER BY taken_on DESC LIMIT 1", (source, kind, eid)).fetchone()
    return json.loads(r["payload"]) if r else {}


def build(con, source, kind, day=None, min_severity="medium", limit=10):
    day = day or db.ymd()
    grouped = db.changes_on(con, source, day, min_severity)
    items = []
    for eid, chs in grouped.items():
        payload = _latest_payload(con, source, kind, eid)
        top = max(ORDER.get(c["severity"], 0) for c in chs)
        sev = [k for k, v in ORDER.items() if v == top][0]
        score = min(100, sum(SEVERITY_POINTS.get(c["severity"], 0) for c in chs)
                    + int(payload.get("base_score") or 0) // 3)
        triggers, why, actions = [], [], []
        for c in sorted(chs, key=lambda x: -ORDER.get(x["severity"], 0)):
            if c["event"] in ("NEW", "GONE"):
                s, w, acts = EVENT[source][c["event"]]
                triggers.append(f'{MARK[s]} {c["event"]}')
                why.append(w); actions += acts
                continue
            r = rule_for(source, c["field"])
            label = FIELD_LABEL.get(source, {}).get(c["field"], c["field"])
            triggers.append(
                f'{MARK[c["severity"]]} {label}: {fmt(c["field"], c["old_value"])}'
                f' -> {fmt(c["field"], c["new_value"])}')
            if r:
                why.append(r[1]); actions += r[2]
        seen, uniq = set(), []
        for a in actions:
            if a not in seen:
                seen.add(a); uniq.append(a)
        items.append({"entity_id": eid, "severity": sev, "score": score,
                      "payload": payload, "triggers": triggers,
                      "why": why[:3], "actions": uniq[:5],
                      "n_changes": len(chs)})
    items.sort(key=lambda x: (-ORDER[x["severity"]], -x["score"]))
    return items[:limit], day


FIELD_LABEL = {
  "us": {
    "estimated_solicitation_release": "Estimated solicitation release",
    "set_aside": "Set-aside", "small_business_program": "Small business program",
    "vehicle": "Contract vehicle", "naics": "NAICS", "status": "Status",
    "contract_number": "Current contract", "incumbent": "Incumbent",
    "dollar_range": "Dollar range", "future_contract_complete": "PoP end",
    "competition": "Competition", "component": "Component", "title": "Title",
    "published_date": "Forecast published",
  },
  "kr": {
    "bid_clse_date": "입찰마감일", "asign_bdgt_amt": "배정예산",
    "bid_ntce_sttus": "공고상태", "bidprc_indstryty": "참가가능업종",
    "prtcpt_psbl_rgn": "참가가능지역", "cntrct_mthd_nm": "계약체결방법",
    "period_end": "계약종료일", "openg_date": "개찰일자",
    "presnatn_date": "설명회일자", "qlfct_rgst_clse_date": "참가자격등록마감",
    "presmpt_prce": "추정가격", "amount": "계약금액", "supplier": "수행업체",
    "ntce_ofcl_tel": "담당자연락처", "title": "사업명",
  },
}

HEAD_KO = {"us": "CAPTURE TRIGGER", "kr": "영업신호"}


def render_markdown(items, source, day, lang=None):
    lang = lang or ("en" if source == "us" else "ko")
    en = lang == "en"
    d = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    L = []
    if en:
        L += [f"# Capture Trigger Brief — {d}", "",
              f"**{len(items)} trigger(s) changed.** Only changes are listed. "
              f"No change means nothing is sent.", ""]
    else:
        L += [f"# 오늘의 변화 브리프 — {d}", "",
              f"**{len(items)}건이 바뀌었습니다.** 바뀐 것만 보냅니다. "
              f"바뀐 게 없으면 발송하지 않습니다.", ""]
    if not items:
        L.append("_No qualifying change today._" if en else "_오늘은 기준을 넘는 변화가 없습니다._")
        return "\n".join(L)

    for it in items:
        p = it["payload"]
        tag = SEVERITY_LABEL[it["severity"]][0 if en else 1]
        L.append("---")
        L.append(f"## [{tag}] {p.get('title') or it['entity_id']}")
        meta = []
        for k, lab_en, lab_ko in (
                ("org", "Agency", "기관"), ("incumbent", "Incumbent", "현 수행업체"),
                ("contract_number", "Current contract", "현 계약번호"),
                ("industry", "NAICS", "업종"), ("lane", "Lane", "구분"),
                ("value", "Value", "금액"), ("key_date", "Key date", "핵심일자"),
                ("end_date", "PoP end", "계약종료")):
            if p.get(k):
                meta.append(f"**{lab_en if en else lab_ko}:** {fmt(k, str(p[k]))}")
        if meta:
            L.append("  \n".join(meta)); L.append("")
        L.append("### " + ("Trigger" if en else "무엇이 바뀌었나"))
        L += [f"- {t}" for t in it["triggers"]]
        L.append("")
        L.append("### " + ("Why this matters" if en else "왜 중요한가"))
        L += [f"- {w}" for w in it["why"]]
        L.append("")
        L.append("### " + ("Recommended actions" if en else "지금 할 일"))
        L += [f"{i}. {a}" for i, a in enumerate(it["actions"], 1)]
        L.append("")
        if p.get("url"):
            L.append(("**Source:** " if en else "**출처:** ") + p["url"])
        L.append(("**Signal score:** " if en else "**신호 점수:** ") + f"{it['score']}/100")
        L.append("")
    L += ["---", "",
          ("Scores and dates are computed by rules from source fields. "
           "No figure is generated by a language model." if en else
           "점수와 날짜는 원문 필드에서 규칙으로 계산합니다. 어떤 수치도 언어모델이 만들지 않습니다.")]
    return "\n".join(L)
