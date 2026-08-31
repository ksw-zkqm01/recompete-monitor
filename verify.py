import sys, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import db, score
from radar.renewal import find_renewals

con = db.connect(); cust = yaml.safe_load(open('customers.yaml', encoding='utf-8'))[0]
print("=== 스코어링 판정 (DB 전 건) ===")
for r in con.execute("SELECT * FROM bid ORDER BY bid_ntce_no"):
    s, reasons, fail = score.score_bid(r, cust)
    v = f"탈락: {fail}" if fail else f"{s}점 -> {'발송' if s>=cust['min_score'] else '보류(기준미달)'}"
    print(f"\n[{r['bid_ntce_no']}] {r['bid_ntce_nm']}")
    print(f"   판정: {v}")
    for x in reasons: print(f"     · {x}")
print("\n=== 재발주 레이더 ===")
for x in find_renewals(con, cust):
    print(f" D-{x['d_day']:>3} | {x['institution']} | {x['contract_name']}")
    print(f"        계약기간 {x['period_raw']} | {x['amount']:,}원")
    print(f"        현 수행업체 {x['supplier']} ({x['supplier_tel'] or '-'})"
          f" | 발주담당 {x['instt_ofcl'] or '-'} {x['instt_tel'] or ''}")
n = con.execute("SELECT COUNT(*) c FROM bid").fetchone()['c']
print(f"\nDB: 공고 {n}건 / 계약 {con.execute('SELECT COUNT(*) c FROM contract').fetchone()['c']}건"
      f" / 낙찰 {con.execute('SELECT COUNT(*) c FROM scsbid').fetchone()['c']}건")
