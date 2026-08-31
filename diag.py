# -*- coding: utf-8 -*-
"""수집·매칭이 어디서 끊겼는지 확인한다."""
import sys, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import db
from radar.score import INDUSTRY_KEYWORDS, _norm

con = db.connect()
cust = (yaml.safe_load(open('customers.yaml', encoding='utf-8')) or [{}])[0]

def q(sql, *a):
    return con.execute(sql, a).fetchone()

print("=" * 62)
print(" 1. DB 적재량")
print("=" * 62)
for t, dcol in (("bid", "bid_ntce_date"), ("contract", "concl_date"), ("scsbid", "opening_date")):
    n = q(f"SELECT COUNT(*) c FROM {t}")["c"]
    r = q(f"SELECT MIN({dcol}) a, MAX({dcol}) b FROM {t}")
    print(f"  {t:<10} {n:>7}건   기간 {r['a'] or '-'} ~ {r['b'] or '-'}")

nw = q("SELECT COUNT(*) c FROM scsbid WHERE winner IS NOT NULL AND winner<>''")["c"]
ns = q("SELECT COUNT(*) c FROM contract WHERE supplier IS NOT NULL AND supplier<>''")["c"]
print(f"\n  낙찰 중 업체명 있는 건 : {nw}")
print(f"  계약 중 업체명 있는 건 : {ns}")

if q("SELECT COUNT(*) c FROM scsbid")["c"] == 0 and q("SELECT COUNT(*) c FROM contract")["c"] == 0:
    print("\n  >>> 수집이 안 됐습니다. TOOLS.bat 3번(SCSBID), 2번(CONTRACTS)을 먼저 실행하세요.")
    sys.exit(0)

print("\n" + "=" * 62)
print(" 2. 실제 사업명 샘플 (낙찰 20건)")
print("=" * 62)
for r in con.execute("SELECT notice_name, winner, winner_amount FROM scsbid "
                     "WHERE winner<>'' ORDER BY winner_amount DESC LIMIT 20"):
    print(f"  {(r['notice_name'] or '')[:52]:<54} | {(r['winner'] or '')[:16]}")

print("\n" + "=" * 62)
print(" 3. 키워드별 적중 건수")
print("=" * 62)
dic = INDUSTRY_KEYWORDS.get(cust.get("industry", "cctv"), INDUSTRY_KEYWORDS["cctv"])
pool = [("핵심", k) for k in dic["core"]] + [("인접", k) for k in dic["adjacent"]] \
     + [("고객", k) for k in cust.get("keywords_include", [])]
rows_s = [(_norm(r["notice_name"]), r) for r in
          con.execute("SELECT notice_name FROM scsbid WHERE winner<>''")]
rows_c = [(_norm(r["contract_name"]), r) for r in
          con.execute("SELECT contract_name FROM contract WHERE supplier<>''")]
tot = 0
for tag, k in pool:
    kn = _norm(k)
    if not kn:
        continue
    a = sum(1 for n, _ in rows_s if kn in n)
    b = sum(1 for n, _ in rows_c if kn in n)
    if a or b:
        print(f"  [{tag}] {k:<16} 낙찰 {a:>5}  계약 {b:>5}")
        tot += a + b
if tot == 0:
    print("  적중 0건. 수집된 데이터에 CCTV 관련 사업이 없거나,")
    print("  사업명 표기가 사전과 다릅니다. 위 2번 샘플을 보고 사전을 보정해야 합니다.")

print("\n" + "=" * 62)
print(" 4. 'CCTV' 글자가 들어간 건 전수 (사전과 무관하게)")
print("=" * 62)
for tbl, col, who in (("scsbid", "notice_name", "winner"), ("contract", "contract_name", "supplier")):
    rs = con.execute(f"SELECT {col} nm, {who} co FROM {tbl} "
                     f"WHERE UPPER({col}) LIKE '%CCTV%' OR {col} LIKE '%영상%' "
                     f"OR {col} LIKE '%관제%' OR {col} LIKE '%방범%' LIMIT 15").fetchall()
    print(f"  -- {tbl}: {len(rs)}건(최대15) --")
    for r in rs:
        print(f"     {(r['nm'] or '')[:50]:<52} | {(r['co'] or '')[:16]}")
