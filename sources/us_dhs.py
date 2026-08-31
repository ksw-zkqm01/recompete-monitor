# -*- coding: utf-8 -*-
"""US 어댑터 — DHS APFS.

[2026-08-30 수정 — 라이브 검증으로 확인된 사실]
1) 기존 CSV 엔드포인트 `https://apfs-cloud.dhs.gov/forecast/?action=csv` 는
   CSV가 아니라 HTML을 돌려준다(200, text/html). 그래서 수집이 0건이었다.
   실제 데이터는 JSON API `https://apfs-cloud.dhs.gov/api/forecast/` 에 있다. (844건 확인)
2) `contract_status` 값은 NEW / REC / NLR 코드다. 'Follow-on' 문자열이 아니다.
   Follow-on 판별은 `competitive` 필드로 한다:
     'Follow-on to Existing Contract' (276) / 'New Requirement, No Contract' (561)
     / 'No Longer Required' (7)
   기존 프로토타입의 `"follow" in contract_status` 필터는 절대 매칭되지 않는다.
3) `naics` 는 "541512 - Computer Systems Design Services" 형식. " - " 앞이 코드.
4) `dollar_range` 는 dict — display_name 을 쓴다.
5) 날짜는 MM/DD/YYYY.
6) `apfs_number` 앞의 `*` 는 원문 표기 그대로 둔다(변경 표시로 추정, 미확인).
"""
import json
import re
import urllib.request
from datetime import date
from pathlib import Path

from . import _us_proto as proto

SOURCE = "us"
KIND = "forecast"

API_URL = "https://apfs-cloud.dhs.gov/api/forecast/"
TARGET_NAICS = {"541511", "541512", "541513", "541519", "518210"}
FOLLOW_ON = "follow-on to existing contract"


def _fetch_json(url=API_URL, timeout=120):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _d(s):
    """MM/DD/YYYY -> YYYY-MM-DD. 형식이 다르면 원문 그대로 둔다."""
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$", s)
    if not m:
        return s
    y = m.group(3)
    y = ("20" + y) if len(y) == 2 else y
    return f"{y}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


def _naics(x):
    return str(x or "").split(" - ")[0].strip()


def _money(x):
    if isinstance(x, dict):
        return x.get("display_name")
    return x


def _clean(v):
    v = "" if v is None else str(v).strip()
    return "" if v.lower() in ("none", "null", "n/a") else v


def normalize(x: dict) -> dict:
    apfs = _clean(x.get("apfs_number"))
    eid = apfs.lstrip("*") or str(x.get("id") or "")
    sol = _d(x.get("estimated_solicitation_release_date"))
    proto_rec = {
        "apfs_id": eid,
        "component": _clean(x.get("organization")),
        "title": _clean(x.get("requirements_title")),
        "description": _clean(x.get("requirement"))[:2000],
        "naics": _naics(x.get("naics")),
        "status": _clean(x.get("competitive")),
        "competition": "YES" if "follow" in str(x.get("competitive") or "").lower()
                       or "new requirement" in str(x.get("competitive") or "").lower() else "",
        "small_business_program": _clean(x.get("small_business_program")),
        "set_aside": _clean(x.get("small_business_set_aside")),
        "vehicle": _clean(x.get("contract_vehicle")),
        "incumbent": _clean(x.get("contractor")),
        "contract_number": _clean(x.get("contract_number")),
        "estimated_solicitation_release": sol,
        "future_contract_complete": _d(x.get("estimated_period_of_performance_end")),
        "dollar_range": _clean(_money(x.get("dollar_range"))),
        "published_date": _d(x.get("published_date") or x.get("publish_date")),
    }
    scored = proto.score_candidate(dict(proto_rec))
    poc = " ".join(y for y in [_clean(x.get("requirements_contact_first_name")),
                               _clean(x.get("requirements_contact_last_name"))] if y)
    return {
        "entity_id": eid,
        "apfs_number": apfs,
        "title": proto_rec["title"],
        "org": proto_rec["component"],
        "component": proto_rec["component"],
        "incumbent": proto_rec["incumbent"],
        "contract_number": proto_rec["contract_number"],
        "naics": proto_rec["naics"],
        "industry": _clean(x.get("naics")),
        "status": proto_rec["status"],                       # Follow-on / New / No Longer Required
        "contract_status_code": _clean(x.get("contract_status")),   # NEW / REC / NLR
        "current_state": _clean(x.get("current_state")),
        "set_aside": proto_rec["set_aside"],
        "small_business_program": proto_rec["small_business_program"],
        "lane": " / ".join(y for y in [proto_rec["small_business_program"],
                                       proto_rec["set_aside"]] if y) or "",
        "vehicle": proto_rec["vehicle"],
        "contract_type": _clean(x.get("contract_type")),
        "competition": proto_rec["competition"],
        "dollar_range": proto_rec["dollar_range"],
        "value": proto_rec["dollar_range"],
        "estimated_solicitation_release": sol,
        "key_date": sol,
        "award_quarter": _clean(x.get("award_quarter")),
        "future_contract_complete": proto_rec["future_contract_complete"],
        "end_date": proto_rec["future_contract_complete"],
        "published_date": proto_rec["published_date"],
        "previous_published_date": _d(x.get("previous_published_date")
                                      or x.get("previous_publish_date")),
        "last_updated_date": _d(x.get("last_updated_date")),
        "poc_name": poc,
        "poc_email": _clean(x.get("requirements_contact_email")),
        "poc_phone": _clean(x.get("requirements_contact_phone")),
        "pop_state": _clean(x.get("place_of_performance_state")),
        "url": f"https://apfs-cloud.dhs.gov/forecast/{x.get('id')}/" if x.get("id") else None,
        "base_score": scored.get("signal_score", 0),
    }


def fetch(sample: Path | None = None, follow_on_only=True,
          naics=TARGET_NAICS, keyword_filter=False, stats=None) -> list[dict]:
    if sample:
        raw = json.loads(Path(sample).read_text(encoding="utf-8"))
        # 오프라인 샘플은 이미 정규화된 프로토타입 형식이다
        out = []
        for c in raw:
            s = proto.score_candidate(dict(c))
            out.append({**{k: c.get(k) for k in
                           ("title", "component", "incumbent", "contract_number", "naics",
                            "status", "set_aside", "small_business_program", "vehicle",
                            "competition", "dollar_range", "estimated_solicitation_release",
                            "future_contract_complete", "published_date")},
                        "entity_id": c.get("apfs_id"), "org": c.get("component"),
                        "industry": c.get("naics"), "value": c.get("dollar_range"),
                        "key_date": c.get("estimated_solicitation_release"),
                        "end_date": c.get("future_contract_complete"),
                        "lane": " / ".join(y for y in [c.get("small_business_program"),
                                                       c.get("set_aside")]
                                           if y and y.upper() not in ("N/A", "NONE")),
                        "url": c.get("source"), "base_score": s.get("signal_score", 0)})
        return out

    rows = _fetch_json()
    total = len(rows)
    rows = [x for x in rows if _naics(x.get("naics")) in naics] if naics else rows
    after_naics = len(rows)
    if follow_on_only:
        rows = [x for x in rows if FOLLOW_ON in str(x.get("competitive") or "").lower()]
    after_follow = len(rows)
    recs = [normalize(x) for x in rows]
    if keyword_filter:
        recs = [r for r in recs
                if any(t in (str(r.get("title", "")) + " " +
                             str(r.get("industry", ""))).lower()
                       for t in proto.CYBER_IT_TERMS)]
    if stats is not None:
        stats.update({"api_total": total, "after_naics": after_naics,
                      "after_follow_on": after_follow, "final": len(recs)})
    return recs


def coverage(records):
    """기술 GO 게이트 측정용 — 기존 계약번호/수행업체 확보율."""
    n = len(records) or 1
    with_cn = sum(1 for r in records if r.get("contract_number"))
    with_inc = sum(1 for r in records if r.get("incumbent"))
    with_sol = sum(1 for r in records if r.get("estimated_solicitation_release"))
    return {"records": len(records),
            "contract_number_pct": round(100 * with_cn / n, 1),
            "incumbent_pct": round(100 * with_inc / n, 1),
            "solicitation_date_pct": round(100 * with_sol / n, 1)}


def enrich(records, sam_api_key=None):
    cache = {}
    for r in records:
        us = proto.fetch_usaspending_award(r.get("contract_number") or "")
        if us:
            r["usaspending_recipient"] = us.get("recipient_name")
            r["usaspending_end_date"] = us.get("current_end_date")
            r["usaspending_amount"] = us.get("award_amount")
            r["usaspending_last_modified"] = us.get("last_modified_date")
        if sam_api_key:
            n = r.get("naics") or ""
            if n not in cache:
                cache[n] = proto.fetch_sam_candidates(n, sam_api_key)
            sm = proto.best_sam_match({"title": r.get("title"), "naics": n}, cache[n])
            if sm:
                r.update(sm)
    return records
