"""고객 발송용 리포트 렌더링 (HTML + 텍스트 + 알림톡 요약)."""
from datetime import date

CSS = """
body{margin:0;background:#f4f5f7;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#1c1f23}
.wrap{max-width:640px;margin:0 auto;padding:24px 16px}
.hd{background:#0f172a;color:#fff;border-radius:12px;padding:20px 22px}
.hd h1{margin:0;font-size:19px;letter-spacing:-.02em}
.hd p{margin:6px 0 0;font-size:13px;color:#94a3b8}
.card{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:18px 20px;margin:14px 0}
.sc{display:inline-block;font-size:13px;font-weight:700;color:#fff;background:#dc2626;border-radius:999px;padding:3px 11px}
.sc.b{background:#ea580c}.sc.c{background:#64748b}
.tt{font-size:16px;font-weight:700;margin:10px 0 4px;line-height:1.4}
.mt{font-size:13px;color:#475569;margin:2px 0}
.mt b{color:#0f172a}
ul{margin:10px 0 0;padding-left:18px}
li{font-size:13px;color:#334155;margin:3px 0;line-height:1.5}
.why{background:#f8fafc;border-left:3px solid #0f172a;padding:10px 12px;margin:12px 0 0;font-size:13px}
.act{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:10px 12px;margin-top:10px;font-size:13px}
a.btn{display:inline-block;margin-top:12px;background:#0f172a;color:#fff;text-decoration:none;
      padding:9px 14px;border-radius:8px;font-size:13px;font-weight:600}
.ft{font-size:11px;color:#94a3b8;margin-top:22px;line-height:1.7}
.sec{font-size:13px;font-weight:700;color:#0f172a;margin:26px 0 4px;letter-spacing:-.01em}
"""


def _won(v):
    if not v:
        return "미공개"
    if v >= 100_000_000:
        return f"{v/100_000_000:.1f}억원".replace(".0억", "억")
    return f"{v:,}원"


def _grade(s):
    return "" if s >= 85 else ("b" if s >= 75 else "c")


def render_html(cust, bids, renewals, today=None):
    today = today or date.today()
    n = len(bids) + len(renewals)
    h = [f"<style>{CSS}</style><div class='wrap'>",
         "<div class='hd'>",
         f"<h1>{cust['company']} · 오늘의 공공시장 영업신호</h1>",
         f"<p>{today:%Y년 %m월 %d일} · 검토 대상 {n}건 · 기준점수 {cust.get('min_score',75)}점 이상</p>",
         "</div>"]

    if bids:
        h.append("<div class='sec'>신규 사업기회</div>")
    for b in bids:
        r, s = b["row"], b["score"]
        h.append(f"<div class='card'><span class='sc {_grade(s)}'>수주적합도 {s}점</span>")
        h.append(f"<div class='tt'>{r['bid_ntce_nm'] or ''}</div>")
        h.append(f"<div class='mt'>{r['ntce_instt_nm'] or ''}"
                 + (f" · 수요기관 {r['dmnd_instt_nm']}" if r['dmnd_instt_nm'] and r['dmnd_instt_nm'] != r['ntce_instt_nm'] else "")
                 + "</div>")
        h.append(f"<div class='mt'>배정예산 <b>{_won(r['asign_bdgt_amt'])}</b>"
                 f" · 계약방법 {r['cntrct_mthd_nm'] or '-'}</div>")
        h.append("<ul>" + "".join(f"<li>{x}</li>" for x in b["reasons"]) + "</ul>")
        h.append("<div class='act'><b>추천 액션</b><br>"
                 + "<br>".join(b["actions"]) + "</div>")
        if r["bid_ntce_url"]:
            h.append(f"<a class='btn' href=\"{r['bid_ntce_url']}\">공고 원문 보기</a>")
        h.append("</div>")

    if renewals:
        h.append("<div class='sec'>계약 종료 임박 · 재발주 예상</div>")
    for x in renewals:
        h.append("<div class='card'><span class='sc'>재발주 D-%d</span>" % x["d_day"])
        h.append(f"<div class='tt'>{x['contract_name'] or ''}</div>")
        h.append(f"<div class='mt'>{x['institution'] or ''}</div>")
        h.append(f"<div class='mt'>계약금액 <b>{_won(x['amount'])}</b> · "
                 f"계약기간 {x.get('period_raw') or ((x['begin_date'] or '?') + ' ~ ' + (x['end_date'] or '?'))}</div>")
        h.append(f"<div class='mt'>현 수행업체 <b>{x['supplier'] or '미상'}</b>"
                 + (f" · 발주 담당 {x['instt_ofcl']} {x['instt_tel']}" if x.get('instt_tel') else "")
                 + "</div>")
        h.append(f"<div class='why'>{x['why']}</div></div>")

    if not bids and not renewals:
        h.append("<div class='card'><b>오늘은 기준을 넘는 건이 없습니다.</b>"
                 "<div class='mt'>기준 미달 건을 억지로 보내지 않습니다.</div></div>")

    h.append("<div class='ft'>본 메일은 귀사가 신청한 유료 구독 서비스의 계약 이행 정보입니다.<br>"
             "데이터 출처: 공공데이터포털 조달청 나라장터 공공데이터개방표준서비스. "
             "점수·D-day는 공고 원문 필드에 기반한 자동 산출값이며 낙찰을 보장하지 않습니다.<br>"
             "수신설정 변경: {unsub}</div></div>")
    return "".join(h)


def render_text(cust, bids, renewals, today=None):
    today = today or date.today()
    L = [f"[{cust['company']}] 오늘의 공공시장 영업신호 · {today:%Y-%m-%d}", ""]
    for b in bids:
        r = b["row"]
        L += [f"■ 수주적합도 {b['score']}점 | {r['bid_ntce_nm']}",
              f"  기관: {r['ntce_instt_nm']}",
              f"  예산: {_won(r['asign_bdgt_amt'])} | 계약방법: {r['cntrct_mthd_nm'] or '-'}"]
        L += [f"  - {x}" for x in b["reasons"]]
        L += [f"  ▶ {x}" for x in b["actions"]]
        if r["bid_ntce_url"]:
            L.append(f"  {r['bid_ntce_url']}")
        L.append("")
    for x in renewals:
        L += [f"■ 재발주 D-{x['d_day']} | {x['contract_name']}",
              f"  기관: {x['institution']} | 계약금액: {_won(x['amount'])}",
              f"  현 수행업체: {x['supplier'] or '미상'} | 종료: {x['end_date']}", ""]
    if not bids and not renewals:
        L.append("오늘은 기준을 넘는 건이 없습니다.")
    L += ["", "출처: 공공데이터포털 조달청 나라장터 공공데이터개방표준서비스"]
    return "\n".join(L)


def render_alimtalk(cust, bids, renewals):
    """카카오 알림톡 템플릿 변수용 요약(1,000자 제한 고려)."""
    top = bids[0] if bids else None
    return {
        "회사명": cust["company"],
        "건수": str(len(bids) + len(renewals)),
        "대표공고": (top["row"]["bid_ntce_nm"][:40] if top else "-"),
        "대표점수": str(top["score"]) if top else "-",
        "대표예산": _won(top["row"]["asign_bdgt_amt"]) if top else "-",
    }
