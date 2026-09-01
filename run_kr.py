#!/usr/bin/env python3
"""AI 공공시장 영업 레이더

  init                        스키마 생성
  seed-mock                   모의 데이터 적재 (키 없이 테스트)
  inspect                     3개 오퍼레이션 실응답 필드 확인
  collect        --days N     입찰공고 수집
  collect-contracts --days N  계약 수집 (1주일 단위 자동 분할)
  collect-scsbid --days N     낙찰 수집 (1일 단위 × 업무구분 자동 분할)
  leads          --min N      업종 실적 보유 업체 명단 CSV (콜 리스트)
  run [--send]                매칭·스코어링·리포트·발송
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import yaml
from radar import db, report, score
from radar.renewal import find_renewals

OUT = ROOT / "out"


def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def customers():
    return yaml.safe_load((ROOT / "customers.yaml").read_text(encoding="utf-8")) or []


def _client():
    from radar.client import G2BClient
    load_env()
    return G2BClient()


def _drain(gen, sink, con, label, batch=2000, keep=None):
    """keep(item) 가 False면 버린다. 내려받은 수/적재한 수를 따로 센다."""
    buf, seen, kept = [], 0, 0
    for it in gen:
        seen += 1
        if keep and not keep(it):
            if seen % 20000 == 0:
                print(f"  ... 수신 {seen:,}건 / 적재 {kept:,}건", flush=True)
            continue
        buf.append(it)
        if len(buf) >= batch:
            kept += sink(con, buf); buf = []
            print(f"  ... 수신 {seen:,}건 / 적재 {kept:,}건", flush=True)
    if buf:
        kept += sink(con, buf)
    print(f"OK  {label} — 수신 {seen:,}건 중 {kept:,}건 적재")
    return kept


# --- commands --------------------------------------------------------------
def cmd_init(a):
    db.connect(); print(f"OK  스키마 생성: {db.DB_PATH}")


def cmd_seed_mock(a):
    from radar.mock import MOCK_BIDS, MOCK_CONTRACTS, MOCK_SCSBIDS
    con = db.connect()
    print(f"OK  모의 공고 {db.upsert_bids(con, MOCK_BIDS)}건 / "
          f"계약 {db.upsert_contracts(con, MOCK_CONTRACTS)}건 / "
          f"낙찰 {db.upsert_scsbids(con, MOCK_SCSBIDS)}건 적재")


def cmd_inspect(a):
    cli = _client()
    end = date.today() - timedelta(days=1)
    checks = [
        ("bid", {"bidNtceBgnDt": (end - timedelta(days=1)).strftime("%Y%m%d0000"),
                 "bidNtceEndDt": end.strftime("%Y%m%d2359")}),
        ("contract", {"cntrctCnclsBgnDate": (end - timedelta(days=6)).strftime("%Y%m%d"),
                      "cntrctCnclsEndDate": end.strftime("%Y%m%d")}),
        ("scsbid", {"bsnsDivCd": "5",
                    "opengBgnDt": end.strftime("%Y%m%d0000"),
                    "opengEndDt": end.strftime("%Y%m%d2359")}),
    ]
    for op, params in checks:
        try:
            item, total = cli.probe(op, params)
            print(f"\n===== {op} (totalCount={total}) =====")
            print(json.dumps(item, ensure_ascii=False, indent=1)[:3000])
        except Exception as e:
            print(f"\n===== {op} ===== 실패: {e}")


def cmd_collect(a):
    cli, con = _client(), db.connect()
    end = date.today(); bgn = end - timedelta(days=a.days)
    print(f"입찰공고 수집 {bgn} ~ {end}")
    _drain(cli.bids(bgn, end, num_rows=a.rows), db.upsert_bids, con, "입찰공고")


def cmd_collect_contracts(a):
    cli, con = _client(), db.connect()
    end = date.today(); bgn = end - timedelta(days=a.days)
    print(f"계약 수집 {bgn} ~ {end}  (1주일 단위 {a.days//7+1}구간 분할)")
    _drain(cli.contracts(bgn, end, num_rows=a.rows), db.upsert_contracts, con, "계약")


def cmd_collect_contracts2(a):
    """계약정보서비스 수집 — 계약기간(만기일)이 채워지는 원천.
    개방표준 계약수집(collect-contracts)을 대체한다."""
    cli, con = _client(), db.connect()
    end = date.today() - timedelta(days=a.offset)
    bgn = end - timedelta(days=a.days)
    print(f"계약(계약정보서비스) 수집 {bgn} ~ {end}  용역+물품, 1주 단위 분할")
    n = _drain(cli.contracts_svc(bgn, end, num_rows=a.rows),
               db.upsert_contracts2, con, "계약(기간포함)")
    tp = con.execute("SELECT COUNT(*) FROM contract WHERE period_end IS NOT NULL "
                     "AND period_end <> ''").fetchone()[0]
    print(f"OK  기간정보 보유 계약: {tp:,}건")


def cmd_collect_scsbid(a):
    cli, con = _client(), db.connect()
    end = date.today(); bgn = end - timedelta(days=a.days)
    cds = a.div.split(",")
    print(f"낙찰 수집 {bgn} ~ {end}  업무구분 {','.join(cds)}")
    print("  주의: 낙찰 API는 '투찰업체마다 1행'입니다. 최종낙찰 행만 골라 적재합니다.")

    def keep(it):
        # 최종낙찰업체가 찍힌 행만 남긴다 (투찰만 하고 떨어진 업체 행은 버림)
        return bool((it.get("fnlSucsfCorpNm") or "").strip())

    _drain(cli.scsbids(bgn, end, bsns_div_cds=cds, num_rows=a.rows),
           db.upsert_scsbids, con, "낙찰", keep=keep)


def cmd_merge_store(a):
    """일일 수집분(data/radar.sqlite3)에서 업종 키워드 일치 행만 걸러
    누적 저장소(data/kr_store.sqlite3)로 병합한다. GitHub Actions 전용.

    저장소 파일은 저장소(repo)에 커밋되어 다음 실행으로 이어진다.
    그래서 매일 7일치만 수집해도 계약종료(D-90) 이력이 계속 쌓인다."""
    from radar.score import INDUSTRY_KEYWORDS, _norm
    dic = INDUSTRY_KEYWORDS.get(a.industry, INDUSTRY_KEYWORDS["cctv"])
    kws = [_norm(k) for k in dic["core"] + dic["adjacent"]]

    def match(name):
        n = _norm(name)
        return any(k in n for k in kws)

    src = db.connect()                                       # 오늘 수집분
    dst = db.connect(ROOT / "data" / "kr_store.sqlite3")     # 누적 저장소

    def copy(table, name_col):
        cols = [c[1] for c in src.execute(f"PRAGMA table_info({table})")]
        ins = (f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
               f"VALUES ({','.join('?' * len(cols))})")
        n, batch = 0, []
        for r in src.execute(f"SELECT * FROM {table}"):
            if not match(r[name_col]):
                continue
            batch.append(tuple(r[c] for c in cols)); n += 1
            if len(batch) >= 2000:
                dst.executemany(ins, batch); batch = []
        if batch:
            dst.executemany(ins, batch)
        dst.commit()
        return n

    nb = copy("bid", "bid_ntce_nm")
    nc = copy("contract", "contract_name")
    ns = copy("scsbid", "notice_name")   # 낙찰 이력 — 수주실적·고착도 배점의 근거

    today = date.today()
    bid_cut = (today - timedelta(days=a.bid_keep)).strftime("%Y%m%d")
    ct_cut = (today - timedelta(days=a.ct_keep)).strftime("%Y%m%d")
    old_cut = (today - timedelta(days=400)).strftime("%Y%m%d")
    d1 = dst.execute("DELETE FROM bid WHERE bid_clse_date IS NOT NULL "
                     "AND bid_clse_date <> '' AND bid_clse_date < ?", (bid_cut,)).rowcount
    # 계약: 종료일이 '있고' 이미 한참 지난 것만 삭제.
    # 종료일 미상 건은 보존한다 — 개방표준 API의 cntrctPrd 는 실측 결과
    # 채움률이 1% 미만이라, 미상을 지우면 계약 데이터가 전멸한다.
    # (수행업체·연락처·체결일이 있는 리드 데이터이므로 남긴다)
    d2 = dst.execute("DELETE FROM contract WHERE period_end IS NOT NULL "
                     "AND period_end <> '' AND period_end < ?", (ct_cut,)).rowcount
    d3 = dst.execute("DELETE FROM contract WHERE (period_end IS NULL OR period_end='') "
                     "AND concl_date IS NOT NULL AND concl_date < ?", (old_cut,)).rowcount
    # 낙찰 이력은 2년 보존 (실적·고착도 판단 근거)
    scs_cut = (today - timedelta(days=730)).strftime("%Y-%m-%d")
    d4 = dst.execute("DELETE FROM scsbid WHERE opening_date IS NOT NULL "
                     "AND opening_date <> '' AND opening_date < ?", (scs_cut,)).rowcount
    dst.commit()
    dst.execute("VACUUM")
    tb = dst.execute("SELECT COUNT(*) FROM bid").fetchone()[0]
    tc = dst.execute("SELECT COUNT(*) FROM contract").fetchone()[0]
    tp = dst.execute("SELECT COUNT(*) FROM contract WHERE period_end IS NOT NULL "
                     "AND period_end <> ''").fetchone()[0]
    ts = dst.execute("SELECT COUNT(*) FROM scsbid").fetchone()[0]
    print(f"OK  병합(+): 공고 {nb:,} / 계약 {nc:,} / 낙찰 {ns:,}건 — '{a.industry}' 키워드 일치분만")
    print(f"OK  정리(-): 마감지난 공고 {d1:,} / 종료지난 계약 {d2:,} / "
          f"기간미상 오래된 계약 {d3:,} / 2년 지난 낙찰 {d4:,}건")
    print(f"OK  저장소 누적: 공고 {tb:,} / 계약 {tc:,}(기간보유 {tp:,}) / "
          f"낙찰 {ts:,}건 -> data/kr_store.sqlite3")


def cmd_leads(a):
    from radar.leads import build, to_csv
    con = db.connect()
    cust = customers()[0] if customers() else {"industry": "cctv"}
    rows = build(con, cust, min_amount=a.min)
    OUT.mkdir(exist_ok=True)
    p = OUT / f"leads_{date.today():%Y%m%d}.csv"
    to_csv(rows, p)
    print(f"OK  업체 {len(rows)}곳 추출 -> {p}\n")
    print(f"{'업체명':<24}{'수주':>4}{'누적금액':>16}  전화번호")
    print("-" * 72)
    for r in rows[:25]:
        print(f"{(r['company'] or '')[:22]:<24}{r['wins']:>4}{r['total']:>16,}  {r['tel'] or '-'}")
    if len(rows) > 25:
        print(f"... 외 {len(rows)-25}곳 (CSV 참조)")


def cmd_run(a):
    load_env()
    con = db.connect(); OUT.mkdir(exist_ok=True)
    today = date.today(); ymd = today.strftime("%Y%m%d")
    summary = []

    for cust in customers():
        rows = con.execute(
            "SELECT * FROM bid WHERE bid_clse_date IS NULL OR bid_clse_date >= ? "
            "ORDER BY bid_ntce_date DESC LIMIT 5000", (ymd,)).fetchall()
        scored = []
        for r in rows:
            key = f"{r['bid_ntce_no']}-{r['bid_ntce_ord']}"
            if not a.resend and db.already_sent(con, cust["id"], key, "bid"):
                continue
            s, reasons, fail = score.score_bid(r, cust, today)
            if fail or s < cust.get("min_score", 75):
                continue
            scored.append({"row": r, "score": s, "reasons": reasons,
                           "actions": score.action_hint(r, s), "key": key})
        scored.sort(key=lambda x: -x["score"])
        scored = scored[: cust.get("max_items", 3)]

        rens = []
        if cust.get("renewal_radar"):
            for x in find_renewals(con, cust, today):
                if not a.resend and db.already_sent(con, cust["id"], x["contract_no"], "renewal"):
                    continue
                rens.append(x)
            rens = rens[:2]

        html = report.render_html(cust, scored, rens, today)
        text = report.render_text(cust, scored, rens, today)
        f = OUT / f"{cust['id']}_{ymd}.html"
        f.write_text(html.replace("{unsub}", os.getenv("UNSUB_URL", "")), encoding="utf-8")

        res = {"sent": False, "reason": "no_items"}
        if scored or rens:
            from radar.mailer import send_email
            subj = f"[영업레이더] {cust['company']} · 오늘 확인할 {len(scored)+len(rens)}건"
            res = send_email(cust["email"], subj, html, text, dry_run=not a.send)
            if res.get("sent"):
                for x in scored:
                    db.mark_sent(con, cust["id"], x["key"], "bid", x["score"])
                for x in rens:
                    db.mark_sent(con, cust["id"], x["contract_no"], "renewal", 0)
        summary.append((cust["company"], len(scored), len(rens), str(f), res))

    print(f"\n{'고객':<18}{'신규':>5}{'재발주':>7}  발송        리포트")
    print("-" * 90)
    for c, nb, nr, path, res in summary:
        flag = "전송" if res.get("sent") else f"미전송({res.get('reason')})"
        print(f"{c:<18}{nb:>5}{nr:>7}  {flag:<12}{path}")


def main():
    p = argparse.ArgumentParser(description="AI 공공시장 영업 레이더")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    sub.add_parser("seed-mock").set_defaults(fn=cmd_seed_mock)
    sub.add_parser("inspect").set_defaults(fn=cmd_inspect)

    c = sub.add_parser("collect"); c.add_argument("--days", type=int, default=2)
    c.add_argument("--rows", type=int, default=999); c.set_defaults(fn=cmd_collect)

    cc = sub.add_parser("collect-contracts"); cc.add_argument("--days", type=int, default=90)
    cc.add_argument("--rows", type=int, default=999); cc.set_defaults(fn=cmd_collect_contracts)

    c2 = sub.add_parser("collect-contracts2"); c2.add_argument("--days", type=int, default=7)
    c2.add_argument("--rows", type=int, default=999)
    c2.add_argument("--offset", type=int, default=0,
                    help="과거 심층 백필용: 오늘로부터 N일 전을 종료일로 수집")
    c2.set_defaults(fn=cmd_collect_contracts2)

    cs = sub.add_parser("collect-scsbid"); cs.add_argument("--days", type=int, default=7)
    cs.add_argument("--rows", type=int, default=999)
    cs.add_argument("--div", default="1,5", help="업무구분코드 1물품 2외자 3공사 5용역")
    cs.set_defaults(fn=cmd_collect_scsbid)

    ms = sub.add_parser("merge-store")
    ms.add_argument("--industry", default="cctv")
    ms.add_argument("--bid-keep", type=int, default=60, help="마감 후 보존일수")
    ms.add_argument("--ct-keep", type=int, default=30, help="계약종료 후 보존일수")
    ms.set_defaults(fn=cmd_merge_store)

    lg = sub.add_parser("leads"); lg.add_argument("--min", type=int, default=0)
    lg.set_defaults(fn=cmd_leads)

    r = sub.add_parser("run")
    r.add_argument("--send", action="store_true")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--resend", action="store_true")
    r.set_defaults(fn=cmd_run)

    a = p.parse_args()
    try:
        a.fn(a)
    except Exception as e:
        from radar.client import G2BError
        if isinstance(e, G2BError):
            print("\n[오류] " + str(e))
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
