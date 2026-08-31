#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recompete / Capture-Trigger Platform — 한국(나라장터) + 미국(DHS APFS) 공용 엔진

  snapshot --source us [--sample dhs_recompete_sample_20.json]
  snapshot --source kr [--kind opportunity|contract]
  diff     --source us|kr [--kind ...]
  brief    --source us|kr [--min high|medium|low] [--limit 10]
  pipeline --source us|kr        (snapshot -> diff -> brief 한 번에)
  simulate --source us           (변화 엔진 데모: 어제/오늘 두 스냅샷을 만들어 diff)
"""
import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from core import brief as briefmod
from core import db, diff

OUT = ROOT / "out"
KINDS = {"us": ["forecast"], "kr": ["opportunity", "contract"]}


def _load(source, kind, args):
    if source == "us":
        from sources import us_dhs
        return us_dhs.fetch(sample=Path(args.sample) if args.sample else None)
    from sources import kr_g2b
    return (kr_g2b.fetch_opportunities() if kind == "opportunity"
            else kr_g2b.fetch_contracts())


def cmd_republish(a):
    """APFS가 예보를 다시 게시한 날 = 무언가 바뀐 날.
    published_date / previous_published_date 는 레코드에 실제로 들어있는 값이다.
    스냅샷 2일치를 기다리지 않고도 '진짜 변화'를 오늘 뽑아낼 수 있다."""
    from datetime import datetime
    from sources import us_dhs
    if a.source != "us":
        print("republish 는 --source us 전용입니다 (APFS 재게시 이력 기반)."); return
    day = a.day or db.ymd()
    iso = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    recs = us_dhs.fetch(sample=Path(a.sample) if a.sample else None)
    hit = [r for r in recs if (r.get("published_date") or "") == iso]
    ref = datetime.strptime(iso, "%Y-%m-%d").date()

    def days_to(s):
        try:
            return (datetime.strptime(s, "%Y-%m-%d").date() - ref).days
        except Exception:
            return None

    items = []
    for r in hit:
        trig, why, acts = [], [], []
        prev = r.get("previous_published_date")
        if prev:
            trig.append(f'[HIGH] Forecast republished: {prev} -> {r["published_date"]}')
            why.append("The agency reissued this forecast entry. Something in the acquisition "
                       "package moved; the requirement is actively being managed.")
            acts += ["Diff this entry against your last saved copy",
                     "Check SAM.gov for a matching notice posted since the previous publish date"]
        else:
            trig.append(f'[HIGH] First appearance in the forecast ({r["published_date"]})')
            why.append("A new follow-on requirement entered the forecast.")
            acts += ["Confirm the incumbent and current contract on USAspending",
                     "Check SAM.gov for prior Sources Sought activity"]
        n = days_to(r.get("key_date") or "")
        if n is not None:
            if n < 0:
                trig.append(f'[HIGH] Estimated solicitation date already passed by {-n} days '
                            f'({r["key_date"]})')
                why.append("The forecast date is behind the calendar while the entry is still "
                           "being republished. The capture window is still open, and the "
                           "acquisition package is close enough to verify directly.")
                acts += ["Verify on SAM.gov whether the solicitation is already out",
                         "Contact the listed POC with one specific acquisition question"]
            elif n <= 90:
                trig.append(f'[HIGH] Estimated solicitation in {n} days ({r["key_date"]})')
                why.append("A near-term solicitation window with a known incumbent.")
                acts += ["Lock capture and proposal resources for this window",
                         "Refresh incumbent-displacement analysis"]
            else:
                trig.append(f'[MED] Estimated solicitation in {n} days ({r["key_date"]})')
                why.append("Long-horizon entry; track rather than staff.")
                acts += ["Set a re-check date 60 days before the forecast date"]
        if r.get("vehicle"):
            acts.append(f'Confirm you can transact on {r["vehicle"]}')
        seen, uniq = set(), []
        for x in acts:
            if x not in seen:
                seen.add(x); uniq.append(x)
        sev = "high" if any(t.startswith("[HIGH]") for t in trig) else "medium"
        score = min(100, 40 + (30 if prev else 15)
                    + (25 if (n is not None and n < 0) else 15 if (n is not None and n <= 90) else 5)
                    + int(r.get("base_score") or 0) // 10)
        items.append({"entity_id": r["entity_id"], "severity": sev, "score": score,
                      "payload": r, "triggers": trig, "why": why[:3],
                      "actions": uniq[:5], "n_changes": len(trig)})
    items.sort(key=lambda x: -x["score"])
    md = briefmod.render_markdown(items, "us", day, lang=a.lang or "en")
    OUT.mkdir(exist_ok=True)
    f = OUT / f"capture_trigger_{day}.md"
    f.write_text(md, encoding="utf-8")
    print(f"OK  {iso} APFS 재게시 {len(hit)}건 -> {f}")
    if a.show:
        print("\n" + md)


def cmd_probe(a):
    """라이브 소스 진단 — 필터 단계별 건수와 GO 게이트 확보율."""
    if a.source != "us":
        from sources import kr_g2b
        try:
            o = kr_g2b.fetch_opportunities(); c = kr_g2b.fetch_contracts()
        except FileNotFoundError as e:
            print(e); return
        print(f"kr/opportunity {len(o)}건 · kr/contract(종료일 있는 건) {len(c)}건")
        if not o:
            print("  -> bid 테이블이 비었습니다. KR_MENU 1번(BIDS)을 먼저 실행하세요.")
        if not c:
            print("  -> contract 테이블이 비었거나 계약기간 파싱이 안 됐습니다. 2번(CONTRACTS) 실행.")
        return
    from sources import us_dhs
    st = {}
    recs = us_dhs.fetch(sample=Path(a.sample) if a.sample else None, stats=st)
    print("필터 단계별:", json.dumps(st, ensure_ascii=False))
    print("확보율(GO 게이트 70%):", json.dumps(us_dhs.coverage(recs), ensure_ascii=False))
    print()
    for r in recs[:5]:
        print(f'  {r.get("entity_id"):<14}{(r.get("title") or "")[:52]:<54}'
              f'{(r.get("incumbent") or "")[:22]}')


def cmd_snapshot(a):
    con = db.connect()
    day = a.day or db.ymd()
    for kind in ([a.kind] if a.kind else KINDS[a.source]):
        recs = _load(a.source, kind, a)
        n = db.save_snapshot(con, a.source, kind, recs, taken_on=day)
        print(f"OK  {a.source}/{kind}  {n}건 스냅샷 저장 ({day})")


def cmd_diff(a):
    con = db.connect()
    for kind in ([a.kind] if a.kind else KINDS[a.source]):
        rows, s = diff.diff_day(con, a.source, kind, today=a.day, prev=a.prev)
        if rows:
            db.save_changes(con, rows)
        print(f"[{a.source}/{kind}] " + json.dumps(s, ensure_ascii=False))


def cmd_brief(a):
    con = db.connect()
    OUT.mkdir(exist_ok=True)
    for kind in ([a.kind] if a.kind else KINDS[a.source]):
        items, day = briefmod.build(con, a.source, kind, day=a.day,
                                    min_severity=a.min, limit=a.limit)
        md = briefmod.render_markdown(items, a.source, day, lang=a.lang)
        f = OUT / f"brief_{a.source}_{kind}_{day}.md"
        f.write_text(md, encoding="utf-8")
        print(f"OK  {a.source}/{kind}  변화 {len(items)}건 -> {f}")
        if a.show:
            print("\n" + md + "\n")


def cmd_pipeline(a):
    cmd_snapshot(a); cmd_diff(a); cmd_brief(a)


def cmd_simulate(a):
    """엔진이 실제로 변화를 잡는지 보여주는 데모.
    어제 스냅샷을 만들고, 오늘 스냅샷에서 몇 개 필드를 바꿔 넣은 뒤 diff 한다.
    (샘플 데이터로만 동작 — 실데이터에는 손대지 않는다)"""
    if a.source != "us":
        print("simulate 는 --source us 샘플 전용입니다."); return
    from sources import us_dhs
    con = db.connect(ROOT / "data" / "simulate.sqlite3")
    recs = us_dhs.fetch(sample=Path(a.sample or ROOT / "dhs_recompete_sample_20.json"))
    y = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    t = date.today().strftime("%Y%m%d")
    db.save_snapshot(con, "us", "forecast", recs, taken_on=y)

    changed = [dict(r) for r in recs]
    if len(changed) > 3:
        changed[0]["estimated_solicitation_release"] = "2026-11-15"
        changed[1]["set_aside"] = "8(a) Sole Source"
        changed[2]["vehicle"] = "CIO-SP4"
        changed[3]["status"] = "Cancelled"
        changed = changed[:-1]                      # 한 건 사라짐(GONE)
        changed.append({**recs[0], "entity_id": "F2026099999",
                        "title": "CBP Zero Trust Network Access Support (NEW)",
                        "status": "Follow-on"})     # 신규(NEW)
    db.save_snapshot(con, "us", "forecast", changed, taken_on=t)

    rows, s = diff.diff_day(con, "us", "forecast", today=t, prev=y)
    db.save_changes(con, rows)
    print("diff:", json.dumps(s, ensure_ascii=False))
    items, day = briefmod.build(con, "us", "forecast", day=t, min_severity="medium", limit=10)
    md = briefmod.render_markdown(items, "us", day, lang=a.lang or "en")
    OUT.mkdir(exist_ok=True)
    f = OUT / f"SIMULATED_capture_trigger_{t}.md"
    f.write_text(md, encoding="utf-8")
    print(f"OK  시뮬레이션 브리프 -> {f}\n")
    print(md)


def main():
    p = argparse.ArgumentParser(description="Recompete / Capture Trigger Platform")
    p.add_argument("--source", choices=["us", "kr"], required=True)
    p.add_argument("--kind")
    p.add_argument("--day"); p.add_argument("--prev")
    p.add_argument("--sample")
    p.add_argument("--min", default="medium", choices=["high", "medium", "low"])
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--lang", choices=["ko", "en"])
    p.add_argument("--show", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("snapshot", cmd_snapshot), ("diff", cmd_diff),
                     ("brief", cmd_brief), ("pipeline", cmd_pipeline),
                     ("simulate", cmd_simulate), ("probe", cmd_probe),
                     ("republish", cmd_republish)):
        sp = sub.add_parser(name); sp.set_defaults(fn=fn)
    a = p.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
