"""낙찰·계약 데이터에서 '업종에 맞는 실적 보유 업체' 명단을 뽑는다.

이게 콜 리스트다. 공식 명세상 낙찰정보에는 최종낙찰업체의
사업자등록번호·주소·연락전화번호가 포함되어 있다.
"""
import csv
from collections import defaultdict

from .score import INDUSTRY_KEYWORDS, _norm


def _match(text, cust):
    n = _norm(text)
    dic = INDUSTRY_KEYWORDS.get(cust.get("industry", "cctv"), INDUSTRY_KEYWORDS["cctv"])
    pool = dic["core"] + dic["adjacent"] + list(cust.get("keywords_include", []))
    return [k for k in pool if _norm(k) and _norm(k) in n]


def build(con, cust, min_amount=0):
    agg = defaultdict(lambda: {
        "company": "", "ceo": "", "bizrno": "", "tel": "", "addr": "",
        "wins": 0, "total": 0, "max": 0, "last_date": "", "samples": [], "source": set(),
    })

    for r in con.execute("SELECT * FROM scsbid WHERE winner IS NOT NULL AND winner<>''"):
        hits = _match(r["notice_name"] or "", cust)
        if not hits:
            continue
        amt = r["winner_amount"] or 0
        if amt < min_amount:
            continue
        k = (r["winner_bizrno"] or r["winner"]).strip()
        a = agg[k]
        a["company"] = a["company"] or r["winner"]
        a["ceo"] = a["ceo"] or (r["winner_ceo"] or "")
        a["bizrno"] = a["bizrno"] or (r["winner_bizrno"] or "")
        a["tel"] = a["tel"] or (r["winner_tel"] or "")
        a["addr"] = a["addr"] or (r["winner_addr"] or "")
        a["wins"] += 1
        a["total"] += amt
        a["max"] = max(a["max"], amt)
        a["last_date"] = max(a["last_date"], r["opening_date"] or "")
        a["source"].add("낙찰")
        if len(a["samples"]) < 3:
            a["samples"].append(f"{r['notice_name']} ({r['demand_instt'] or r['notice_instt']})")

    for r in con.execute("SELECT * FROM contract WHERE supplier IS NOT NULL AND supplier<>''"):
        hits = _match(r["contract_name"] or "", cust)
        if not hits:
            continue
        amt = r["amount"] or 0
        if amt < min_amount:
            continue
        k = (r["supplier_bizrno"] or r["supplier"]).strip()
        a = agg[k]
        a["company"] = a["company"] or r["supplier"]
        a["ceo"] = a["ceo"] or (r["supplier_ceo"] or "")
        a["bizrno"] = a["bizrno"] or (r["supplier_bizrno"] or "")
        a["tel"] = a["tel"] or (r["supplier_tel"] or "")
        a["addr"] = a["addr"] or (r["supplier_addr"] or "")
        a["wins"] += 1
        a["total"] += amt
        a["max"] = max(a["max"], amt)
        a["last_date"] = max(a["last_date"], r["concl_date"] or "")
        a["source"].add("계약")
        if len(a["samples"]) < 3:
            a["samples"].append(f"{r['contract_name']} ({r['demand_instt'] or r['contract_instt']})")

    rows = list(agg.values())
    rows.sort(key=lambda x: (-x["wins"], -x["total"]))
    return rows


def to_csv(rows, path):
    cols = ["순위", "업체명", "대표자", "사업자번호", "전화번호", "주소",
            "수주건수", "누적금액", "최대건금액", "최근일자", "출처", "대표사업1", "대표사업2", "대표사업3"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i, r in enumerate(rows, 1):
            s = r["samples"] + ["", "", ""]
            w.writerow([i, r["company"], r["ceo"], r["bizrno"], r["tel"], r["addr"],
                        r["wins"], r["total"], r["max"], r["last_date"],
                        "/".join(sorted(r["source"])), s[0], s[1], s[2]])
    return path
