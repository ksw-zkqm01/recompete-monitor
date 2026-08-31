"""계약 종료 임박 = 재발주 예상 레이더.

계약기간(cntrctPrd)은 자유 문자열이라 파싱에 실패할 수 있다.
파싱된 종료일이 있는 건만 다룬다. 추정하지 않는다.
"""
from datetime import date, timedelta

from .score import INDUSTRY_KEYWORDS, _norm, _parse_date


def _hits(text, cust):
    n = _norm(text)
    dic = INDUSTRY_KEYWORDS.get(cust.get("industry", "cctv"), INDUSTRY_KEYWORDS["cctv"])
    pool = dic["core"] + dic["adjacent"] + list(cust.get("keywords_include", []))
    return [k for k in pool if _norm(k) and _norm(k) in n]


def find_renewals(con, cust, today=None, window=(30, 180)):
    today = today or date.today()
    lo = today + timedelta(days=window[0])
    hi = today + timedelta(days=window[1])
    out = []
    for r in con.execute(
            "SELECT * FROM contract WHERE period_end IS NOT NULL AND period_end<>'' "
            "ORDER BY period_end"):
        end = _parse_date(r["period_end"])
        if not end or not (lo <= end <= hi):
            continue
        title = f"{r['contract_name'] or ''} {r['demand_instt'] or ''} {r['contract_instt'] or ''}"
        hits = _hits(title, cust)
        if not hits:
            continue
        if any(_norm(k) in _norm(title) for k in cust.get("keywords_exclude", []) if _norm(k)):
            continue
        amt = r["amount"] or 0
        if cust.get("budget_min") and amt and amt < cust["budget_min"]:
            continue
        instt = r["demand_instt"] or r["contract_instt"] or ""
        regions = cust.get("regions", [])
        rgn_ok = (not regions) or any(_norm(x) in _norm(instt) for x in regions)
        d = (end - today).days
        out.append({
            "contract_no": r["contract_no"],
            "institution": instt,
            "contract_name": r["contract_name"],
            "supplier": r["supplier"],
            "supplier_tel": r["supplier_tel"],
            "amount": amt,
            "period_raw": r["period_raw"],
            "begin_date": r["period_begin"],
            "end_date": r["period_end"],
            "instt_ofcl": r["instt_ofcl"],
            "instt_tel": r["instt_tel"],
            "url": r["contract_url"] or r["bid_url"],
            "d_day": d,
            "keywords": hits,
            "region_match": rgn_ok,
            "why": f"계약 종료 D-{d} · 현 수행업체 {r['supplier'] or '미상'} · "
                   f"직전 계약금액 {amt:,}원" if amt else f"계약 종료 D-{d}",
        })
    out.sort(key=lambda x: (not x["region_match"], x["d_day"]))
    return out
