#!/usr/bin/env python3
"""
Federal Recompete Radar MVP
- APFS -> Follow-on candidates
- USAspending -> incumbent award enrichment
- SAM.gov -> procurement signal enrichment
- Rule-based score -> ranked capture triggers

The script supports offline validation with --sample-json.
Live mode requires internet access. SAM mode also requires SAM_API_KEY.

Official sources:
  USAspending: https://api.usaspending.gov/docs/endpoints
  SAM.gov:     https://open.gsa.gov/api/get-opportunities-public-api/
  DHS APFS:    https://apfs-cloud.dhs.gov/forecast/?action=csv
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
except ImportError:
    requests = None

APFS_CSV_URL = "https://apfs-cloud.dhs.gov/forecast/?action=csv"
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
SAM_URL = "https://api.sam.gov/opportunities/v2/search"

TARGET_NAICS = {"541511", "541512", "541513", "541519", "518210"}
CYBER_IT_TERMS = {
    "cyber", "security", "cloud", "identity", "access management", "iam",
    "zero trust", "devsecops", "network", "software", "application", "data",
    "it support", "information technology", "malware", "threat", "hosting",
    "microsoft 365", "oracle", "infrastructure", "engineering"
}

def parse_date(s: Any):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None

def normalize(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()

def money_upper_bound(text: Any) -> float | None:
    if not text:
        return None
    t = str(text).replace(",", "")
    nums = [float(x) for x in re.findall(r"\$?([0-9]+(?:\.[0-9]+)?)", t)]
    if not nums:
        return None
    if "million" in t.lower():
        nums = [n * 1_000_000 for n in nums]
    return max(nums)

def title_similarity(a: str, b: str) -> float:
    a = normalize(a).lower()
    b = normalize(b).lower()
    if not a or not b:
        return 0.0
    sa = set(re.findall(r"[a-z0-9]+", a))
    sb = set(re.findall(r"[a-z0-9]+", b))
    j = len(sa & sb) / max(1, len(sa | sb))
    seq = SequenceMatcher(None, a, b).ratio()
    return max(j, seq)

def score_candidate(c: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    score = 0
    reasons: list[str] = []

    if "follow" in normalize(c.get("status")).lower():
        score += 25
        reasons.append("Follow-on forecast confirmed (+25)")

    incumbent = normalize(c.get("incumbent"))
    if incumbent and "tbd" not in incumbent.lower():
        score += 10
        reasons.append("Incumbent identified (+10)")

    sol = parse_date(c.get("estimated_solicitation_release"))
    if sol:
        days = (sol - today).days
        if 0 <= days <= 90:
            score += 20
            reasons.append(f"Solicitation expected in {days} days (+20)")
        elif 91 <= days <= 180:
            score += 14
            reasons.append(f"Solicitation expected in {days} days (+14)")
        elif 181 <= days <= 365:
            score += 8
            reasons.append(f"Solicitation expected in {days} days (+8)")
        elif -30 <= days < 0:
            score += 8
            reasons.append(f"Forecast solicitation date passed {-days} days ago; verify SAM now (+8)")
        elif days < -30:
            score += 2
            reasons.append("Forecast solicitation date is stale; SAM verification required (+2)")
        else:
            score += 4
            reasons.append("Long-horizon forecast (+4)")

    pub = parse_date(c.get("published_date"))
    if pub:
        age = (today - pub).days
        if age <= 14:
            score += 10
            reasons.append("Forecast updated within 14 days (+10)")
        elif age <= 45:
            score += 7
            reasons.append("Forecast updated within 45 days (+7)")
        elif age <= 90:
            score += 4
            reasons.append("Forecast updated within 90 days (+4)")

    if normalize(c.get("competition")).upper() == "YES":
        score += 5
        reasons.append("Competition expected (+5)")

    sb = (normalize(c.get("set_aside")) + " " + normalize(c.get("small_business_program"))).lower()
    if sb and sb not in {"n/a none", "none n/a"} and ("full" in sb or "8(a)" in sb or "wosb" in sb or "sb" in sb):
        score += 5
        reasons.append("Small-business lane identified (+5)")

    upper = money_upper_bound(c.get("dollar_range"))
    if upper:
        if upper >= 100_000_000:
            score += 10
            reasons.append("Very high-value requirement (+10)")
        elif upper >= 10_000_000:
            score += 7
            reasons.append("High-value requirement (+7)")
        elif upper >= 2_000_000:
            score += 5
            reasons.append("Material contract value (+5)")
        else:
            score += 3
            reasons.append("Defined contract value (+3)")

    hay = " ".join([
        normalize(c.get("title")),
        normalize(c.get("description")),
        " ".join(c.get("keywords") or []),
    ]).lower()
    if any(term in hay for term in CYBER_IT_TERMS):
        score += 10
        reasons.append("Cyber/IT capability match (+10)")

    if c.get("usaspending_match"):
        score += 5
        reasons.append("USAspending incumbent award matched (+5)")
    if c.get("sam_signal_type"):
        st = normalize(c.get("sam_signal_type")).lower()
        if "sources sought" in st:
            score += 15
            reasons.append("SAM Sources Sought signal (+15)")
        elif "pre" in st:
            score += 12
            reasons.append("SAM Pre-Solicitation signal (+12)")
        elif "solicitation" in st:
            score += 10
            reasons.append("SAM solicitation signal (+10)")
        else:
            score += 5
            reasons.append("SAM activity detected (+5)")

    c = dict(c)
    c["signal_score"] = min(score, 100)
    c["score_reasons"] = reasons
    return c

def load_sample(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))

def fetch_apfs() -> list[dict[str, Any]]:
    if requests is None:
        raise RuntimeError("Install requests: pip install requests")
    r = requests.get(APFS_CSV_URL, timeout=60)
    r.raise_for_status()
    text = r.content.decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))

    def pick(row, *names):
        for n in names:
            if n in row and row[n] not in (None, ""):
                return row[n]
        return None

    out = []
    for row in rows:
        status = normalize(pick(row, "Contract Status"))
        naics = normalize(pick(row, "NAICS")).split(" - ")[0]
        title = normalize(pick(row, "Requirements Title"))
        desc = normalize(pick(row, "Requirement", "Mission"))
        if "follow" not in status.lower():
            continue
        if naics not in TARGET_NAICS:
            continue
        hay = (title + " " + desc).lower()
        if not any(t in hay for t in CYBER_IT_TERMS):
            continue

        out.append({
            "apfs_id": normalize(pick(row, "APFS Number")),
            "component": normalize(pick(row, "Component")),
            "title": title,
            "description": desc,
            "naics": naics,
            "status": status,
            "small_business_program": normalize(pick(row, "Small Business Program")),
            "set_aside": normalize(pick(row, "Small Business Set-Aside")),
            "vehicle": normalize(pick(row, "Contract Vehicle")),
            "incumbent": normalize(pick(row, "Contractor")),
            "contract_number": normalize(pick(row, "Contract Number")),
            "estimated_solicitation_release": normalize(pick(
                row, "Estimated Solicitation Release Date", "Estimated Solicitation Release"
            )),
            "future_contract_complete": normalize(pick(row, "Estimated Period of Performance End")),
            "dollar_range": normalize(pick(row, "Dollar Range")),
            "published_date": normalize(pick(row, "Forecast Published")),
        })
    return out

def contract_id_candidates(raw: str) -> list[str]:
    raw = normalize(raw)
    if not raw or "tbd" in raw.lower():
        return []
    # Extract contract-like tokens. APFS sometimes stores parent + order together.
    tokens = re.findall(r"[A-Z0-9]{8,25}", raw.upper())
    # Preserve order, favor longer IDs.
    uniq = []
    for x in sorted(tokens, key=len, reverse=True):
        if x not in uniq:
            uniq.append(x)
    return uniq[:5]

def fetch_usaspending_award(contract_number: str) -> dict[str, Any] | None:
    if requests is None:
        return None
    ids = contract_id_candidates(contract_number)
    for award_id in ids:
        payload = {
            "subawards": False,
            "limit": 10,
            "page": 1,
            "filters": {
                "award_type_codes": ["A", "B", "C", "D"],
                "award_ids": [award_id],
                "time_period": [{"start_date": "2015-01-01", "end_date": date.today().isoformat()}],
            },
            "fields": [
                "Award ID", "Recipient Name", "Start Date", "End Date", "Award Amount",
                "Awarding Agency", "Awarding Sub Agency", "Contract Award Type",
                "Description", "Last Modified Date", "NAICS", "PSC"
            ],
            "sort": "Last Modified Date",
            "order": "desc",
        }
        r = requests.post(USASPENDING_URL, json=payload, timeout=60)
        if r.status_code != 200:
            continue
        results = r.json().get("results", [])
        exact = [x for x in results if normalize(x.get("Award ID")).upper() == award_id]
        if exact:
            x = exact[0]
            return {
                "matched_award_id": x.get("Award ID"),
                "recipient_name": x.get("Recipient Name"),
                "current_end_date": x.get("End Date"),
                "award_amount": x.get("Award Amount"),
                "award_description": x.get("Description"),
                "last_modified_date": x.get("Last Modified Date"),
                "naics_usaspending": x.get("NAICS"),
                "psc": x.get("PSC"),
            }
    return None

def fetch_sam_candidates(naics: str, api_key: str, days_back: int = 365) -> list[dict[str, Any]]:
    if requests is None:
        return []
    posted_to = date.today()
    posted_from = max(posted_to - timedelta(days=days_back), date(posted_to.year - 1, posted_to.month, posted_to.day))
    params = [
        ("api_key", api_key),
        ("limit", "1000"),
        ("offset", "0"),
        ("postedFrom", posted_from.strftime("%m/%d/%Y")),
        ("postedTo", posted_to.strftime("%m/%d/%Y")),
        ("ncode", naics),
    ]
    # Pull key notice types: Sources Sought, Pre-solicitation, Solicitation, Combined.
    for ptype in ("r", "p", "o", "k"):
        params.append(("ptype", ptype))
    r = requests.get(SAM_URL, params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("opportunitiesData", [])

def best_sam_match(candidate: dict[str, Any], notices: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    best = None
    best_score = 0.0
    for n in notices:
        path = normalize(n.get("fullParentPathName") or n.get("department"))
        if "HOMELAND SECURITY" not in path.upper():
            continue
        sim = title_similarity(candidate.get("title", ""), n.get("title", ""))
        if normalize(candidate.get("naics")) == normalize(n.get("naicsCode")):
            sim += 0.10
        if sim > best_score:
            best_score = sim
            best = n
    if best and best_score >= 0.48:
        return {
            "sam_match_score": round(best_score, 3),
            "sam_notice_id": best.get("noticeId"),
            "sam_title": best.get("title"),
            "sam_solicitation_number": best.get("solicitationNumber"),
            "sam_posted_date": best.get("postedDate"),
            "sam_signal_type": best.get("type") or best.get("baseType"),
            "sam_response_deadline": best.get("responseDeadLine"),
            "sam_set_aside": best.get("typeOfSetAside"),
        }
    return None

def run_live(sam_api_key: str | None) -> list[dict[str, Any]]:
    candidates = fetch_apfs()
    sam_cache: dict[str, list[dict[str, Any]]] = {}
    out = []
    for c in candidates:
        us = fetch_usaspending_award(c.get("contract_number", ""))
        if us:
            c.update(us)
            c["usaspending_match"] = True
        if sam_api_key:
            naics = c.get("naics", "")
            if naics not in sam_cache:
                sam_cache[naics] = fetch_sam_candidates(naics, sam_api_key)
            sm = best_sam_match(c, sam_cache[naics])
            if sm:
                c.update(sm)
        out.append(score_candidate(c))
    return sorted(out, key=lambda x: x["signal_score"], reverse=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample-json", type=Path, help="Offline sample JSON")
    p.add_argument("--output", type=Path, default=Path("recompete_ranked.json"))
    p.add_argument("--sam-api-key", default=os.getenv("SAM_API_KEY"))
    args = p.parse_args()

    if args.sample_json:
        rows = [score_candidate(x, today=date(2026, 8, 29)) for x in load_sample(args.sample_json)]
        rows.sort(key=lambda x: x["signal_score"], reverse=True)
    else:
        rows = run_live(args.sam_api_key)

    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} candidates -> {args.output}")
    for r in rows[:10]:
        print(f'{r["signal_score"]:>3}  {r.get("apfs_id",""):<12}  {r.get("title","")[:80]}')

if __name__ == "__main__":
    main()
