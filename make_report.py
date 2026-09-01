#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""크몽 판매용 맞춤 리포트 생성기 — D-90  (스코어링 중심)

  py -3.11 make_report.py --tier light    --company "○○시스템" --keywords "CCTV,관제" \
       --region 서울 --min 0.1 --max 30 [--licenses "정보통신공사업"] [--mock]

  LIGHT    진행 공고 — 건별 수주 적합도 점수 + 체크리스트 + 권장 조치
  STANDARD + 계약만기(D-90) 재계약 기회 — 건별 적합도 + 지금 할 일
  DEEP     + 낙찰 이력(경쟁 구도) + 접근 전략 노트

원칙: 점수는 고객 조건과 공고 원문 필드의 일치도(사전 정의 규칙 계산)다.
      LLM 생성 수치 없음. 근거는 전부 체크리스트로 표기한다.
"""
import argparse
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out" / "reports"

from radar.score import INDUSTRY_KEYWORDS, _norm, action_hint  # noqa: E402

EOK = 100_000_000


def won(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return "—"
    if v >= EOK:
        s = f"{v/EOK:.1f}".rstrip("0").rstrip(".")
        return f"{s}억원"
    if v >= 10_000:
        return f"{v//10_000:,}만원"
    return f"{v:,}원"


def d8(s):
    s = str(s or "")
    return f"{s[2:4]}.{s[4:6]}.{s[6:8]}" if len(s) >= 8 else "—"


def days_to(s, today):
    try:
        return (datetime.strptime(str(s)[:8], "%Y%m%d").date() - today).days
    except (ValueError, TypeError):
        return None


def _parse8(s):
    try:
        return datetime.strptime(str(s)[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _co_match(winner, bizrno, company, my_bizrno):
    """상호/사업자번호로 '귀사' 여부 판정. 번호가 있으면 번호 우선."""
    if my_bizrno:
        a = re.sub(r"[^0-9]", "", str(bizrno or ""))
        b = re.sub(r"[^0-9]", "", my_bizrno)
        if a and b and a == b:
            return True
    w, c = _norm(winner), _norm(company)
    return bool(w and c and len(c) >= 3 and (c in w or w in c))


def _org_match(a, b):
    na, nb = _norm(a), _norm(b)
    return bool(na and nb and len(min(na, nb, key=len)) >= 4 and (na in nb or nb in na))


class History:
    """낙찰 이력 DB(scsbid) 조회 — 실적·발주처 관계·기존업체 고착도의 근거."""

    def __init__(self, con, cust):
        self.rows = []
        try:
            for r in con.execute(
                    "SELECT notice_name, demand_instt, notice_instt, winner, "
                    "winner_bizrno, winner_amount, opening_date FROM scsbid WHERE winner<>''"):
                self.rows.append(dict(r))
        except sqlite3.OperationalError:
            pass
        self.has = len(self.rows) > 0
        dic = INDUSTRY_KEYWORDS.get(cust.get("industry", "cctv"), INDUSTRY_KEYWORDS["cctv"])
        kws = [_norm(k) for k in dic["core"] + dic["adjacent"] + cust.get("keywords_include", [])]
        self.kws = [k for k in kws if k]
        self.company = cust.get("company", "")
        self.bizrno = cust.get("bizrno", "")

    def _kw(self, name):
        n = _norm(name)
        return any(k in n for k in self.kws)

    def my_wins(self):
        return [r for r in self.rows if self._kw(r["notice_name"])
                and _co_match(r["winner"], r["winner_bizrno"], self.company, self.bizrno)]

    def my_wins_at(self, org):
        return [r for r in self.my_wins()
                if _org_match(r["demand_instt"] or r["notice_instt"], org)]

    def lock_at(self, org):
        """해당 기관의 유사 낙찰에서 최다 수주업체와 횟수. (업체명, 횟수, 표본수)"""
        hits = [r for r in self.rows if self._kw(r["notice_name"])
                and _org_match(r["demand_instt"] or r["notice_instt"], org)]
        if not hits:
            return None, 0, 0
        cnt = {}
        for r in hits:
            cnt[r["winner"]] = cnt.get(r["winner"], 0) + 1
        top = max(cnt, key=cnt.get)
        return top, cnt[top], len(hits)

    def supplier_lock(self, supplier, org):
        n = 0
        for r in self.rows:
            if self._kw(r["notice_name"]) and _org_match(r["demand_instt"] or r["notice_instt"], org) \
               and _norm(r["winner"]) and _norm(supplier) and \
               (_norm(supplier) in _norm(r["winner"]) or _norm(r["winner"]) in _norm(supplier)):
                n += 1
        return n


def _fit_rows(name, cust, cap=25):
    """사업 적합성 (25) — 키워드·업종 일치. (득점, 근거) 또는 None."""
    nn = _norm(name)
    dic = INDUSTRY_KEYWORDS.get(cust.get("industry", "cctv"), INDUSTRY_KEYWORDS["cctv"])
    extra = cust.get("keywords_include", [])
    core = [k for k in dic["core"] + extra if _norm(k) and _norm(k) in nn]
    adj = [k for k in dic["adjacent"] if _norm(k) in nn]
    svc = [k for k in dic["service"] if _norm(k) in nn]
    if core:
        pts = min(cap, 21 + 2 * (len(core) - 1) + (1 if svc else 0))
        return pts, "핵심 키워드 " + ", ".join(core[:3]) + (f" · 사업유형 {svc[0]}" if svc else "")
    if adj:
        return min(18, 14 + 1 * (len(adj) - 1)), "인접 키워드 " + ", ".join(adj[:3])
    return None


def _track_rows(hist):
    """수주 실적 (25) — 낙찰 이력 DB에서 귀사 유사 사업 수주 검색."""
    wins = hist.my_wins()
    if wins:
        ex = " · ".join(f"{w['notice_name'][:18]}({str(w['opening_date'])[2:7]})" for w in wins[:2])
        n = len(wins)
        pts = 25 if n >= 3 else 18 if n == 2 else 14
        return pts, f"유사 사업 수주 {n}건 확인 — {ex}" + (" 외" if n > 2 else "")
    if hist.has:
        return 5, "낙찰 이력 DB(수집분)에서 귀사 수주 기록 미발견 — 실적 증빙 제출 시 재산정"
    return 10, "낙찰 이력 데이터 수집 전 — 중립 처리"


def score_bid_detail(r, cust, today, hist):
    """공고 수주 적합도 — 캡처 실무 기준 배점.
    사업적합 25 · 참가자격 20 · 수주실적 25 · 발주처 15 · 경쟁환경 15 = 100"""
    g = dict(r).get
    name = g("bid_ntce_nm") or ""
    nn = _norm(name)
    warns = []

    for kw in cust.get("keywords_exclude", []):
        if _norm(kw) and _norm(kw) in nn:
            return None, None, None, f"제외키워드 '{kw}'"
    budget = g("asign_bdgt_amt") or g("presmpt_prce") or 0
    bmin, bmax = cust.get("budget_min") or 0, cust.get("budget_max") or 10**15
    if budget and (budget < bmin or budget > bmax):
        return None, None, None, "금액대 밖"
    clse = _parse8(g("bid_clse_date"))
    if clse and clse < today:
        return None, None, None, "마감 경과"

    rows = []

    # 1. 사업 적합성 25
    fit = _fit_rows(name, cust)
    if not fit:
        return None, None, None, "업종 불일치"
    rows.append(("사업적합", fit[0], 25, fit[1]))

    # 2. 참가 자격 20 = 면허 10 + 지역 10 (입찰 참가가 가능한가)
    ind_lmt = (g("indstryty_lmt_yn") or "N").upper()
    ind = g("bidprc_indstryty") or ""
    lic = cust.get("licenses", [])
    if ind_lmt == "Y" and ind:
        if any(_norm(x) and _norm(x) in _norm(ind) for x in lic):
            lp, ln = 10, f"필요업종 '{ind}' — 보유면허 충족"
        else:
            lp, ln = 2, f"필요업종 '{ind}' — 보유 여부 확인 필요"
            warns.append(f"필요업종 '{ind}' 면허 미확인 — 미충족 시 참가 불가")
    else:
        lp, ln = 8, "업종제한 없음"
    rgn_lmt = (g("rgn_lmt_yn") or "N").upper()
    rgn = g("prtcpt_psbl_rgn") or ""
    regions = cust.get("regions", [])
    if rgn_lmt == "Y" and rgn:
        if any(_norm(x) and _norm(x) in _norm(rgn) for x in regions):
            rp, rn = 10, f"지역제한 '{rgn}' 일치 — 경쟁 풀 축소"
        else:
            rp, rn = 2, f"지역제한 '{rgn}' — 영업권역 밖"
            warns.append(f"지역제한 '{rgn}' 충족 여부 확인 — 미충족 시 참가 불가")
    else:
        rp, rn = 8, "지역제한 없음 (전국 경쟁)"
    rows.append(("참가자격", lp + rp, 20, f"{ln} / {rn}"))

    # 3. 수주 실적 25
    tp, tn = _track_rows(hist)
    rows.append(("수주실적", tp, 25, tn))

    # 4. 발주처 관계·고착도 15
    org = g("dmnd_instt_nm") or g("ntce_instt_nm") or ""
    my_at = hist.my_wins_at(org)
    top, topn, sample = hist.lock_at(org)
    if my_at:
        rows.append(("발주처", 15, 15,
                     f"귀사 수주 이력 있는 발주처 — {my_at[0]['notice_name'][:20]}({str(my_at[0]['opening_date'])[2:7]})"))
    elif topn >= 2:
        rows.append(("발주처", 5, 15, f"'{top}' {topn}회 반복 수주 — 기존 업체 고착 신호"))
        warns.append(f"이 기관 유사 사업은 '{top}'가 반복 수주 중 — 차별화 요소 필요")
    elif sample:
        rows.append(("발주처", 10, 15, f"반복 수주 고착 없음 (유사 낙찰 {sample}건 기준)"))
    else:
        rows.append(("발주처", 8, 15, "이 기관의 유사 낙찰 이력 데이터 부족"))

    # 5. 경쟁 환경 15 — 계약방법 + 재공고/긴급 신호
    mth = g("cntrct_mthd_nm") or ""
    if "수의" in mth:
        cp, cn = 15, f"수의계약 — 경쟁 최소"
    elif "협상" in mth:
        cp, cn = 13, "협상에 의한 계약 — 제안 역량 승부"
    elif "지명" in mth:
        cp, cn = 12, "지명경쟁"
    elif "제한" in mth:
        cp, cn = 11, "제한경쟁 — 자격 충족 업체만 경쟁"
    elif mth:
        cp, cn = 9, f"{mth} — 개방 경쟁"
    else:
        cp, cn = 8, "계약방법 미표기"
    st = g("bid_ntce_sttus") or ""
    if "재공고" in st:
        cp = min(15, cp + 2); cn += " · 재공고(직전 유찰) — 경쟁 낮을 가능성"
    if "긴급" in st:
        cp = max(4, cp - 2); cn += " · 긴급공고 — 준비기간 짧음"
    rows.append(("경쟁환경", cp, 15, cn))

    # 경고 (점수 밖)
    if clse:
        d = (clse - today).days
        if d < 3:
            warns.append(f"입찰마감 D-{d} — 준비기간 촉박")
    qr = _parse8(g("qlfct_rgst_clse_date"))
    if qr and qr < today:
        warns.append(f"입찰참가자격 등록마감 경과 ({qr:%Y-%m-%d}) — 참가 가능 여부 확인")
    elif qr and (qr - today).days <= 2:
        warns.append(f"입찰참가자격 등록마감 D-{(qr - today).days}")

    total = sum(p for _, p, _, _ in rows)
    return total, rows, warns, None


def score_renewal_detail(r, cust, d_day, hist):
    """만기 계약 적합도 — 사업적합 25 · 발주처관계 20 · 기존업체 20 · 금액 15 · 재발주임박 20 = 100"""
    name = r["contract_name"] or ""
    nn = _norm(name)
    for kw in cust.get("keywords_exclude", []):
        if _norm(kw) and _norm(kw) in nn:
            return None, None
    rows, warns = [], []

    fit = _fit_rows(name, cust)
    if not fit:
        return None, None
    rows.append(("사업적합", fit[0], 25, fit[1]))

    org = r["demand_instt"] or r["contract_instt"] or ""
    my_at = hist.my_wins_at(org)
    my = hist.my_wins()
    if my_at:
        rows.append(("발주처관계", 20, 20,
                     f"귀사 수주 이력 있는 발주처 — {my_at[0]['notice_name'][:20]}({str(my_at[0]['opening_date'])[2:7]})"))
    elif my:
        rows.append(("발주처관계", 12, 20, f"타 기관 유사 사업 수주 {len(my)}건 — 실적 제시 가능"))
    elif hist.has:
        rows.append(("발주처관계", 5, 20, "낙찰 이력 DB에서 귀사 수주 기록 미발견"))
    else:
        rows.append(("발주처관계", 10, 20, "낙찰 이력 데이터 수집 전 — 중립 처리"))

    sup = r["supplier"] or ""
    if sup and _co_match(sup, None, cust.get("company", ""), cust.get("bizrno", "")):
        rows.append(("기존업체", 20, 20, "현 수행업체 = 귀사 — 재계약 방어전, 최우선 대응"))
    elif sup:
        n = hist.supplier_lock(sup, org)
        if n >= 2:
            rows.append(("기존업체", 6, 20, f"현 수행 '{sup}' — 이 기관 유사 사업 {n}회 수주, 고착 신호"))
            warns.append(f"'{sup}' 고착 발주처 — 단가·유지보수 조건 차별화 없이는 어려움")
        else:
            rows.append(("기존업체", 13, 20, f"현 수행 '{sup}' — 반복 수주 고착 신호 없음(수집분 기준)"))
    else:
        rows.append(("기존업체", 10, 20, "현 수행업체 미공개"))

    amt = r["amount"] or 0
    bmin, bmax = cust.get("budget_min") or 0, cust.get("budget_max") or 10**15
    if amt and bmin <= amt <= bmax:
        span = bmax - bmin
        central = span > 0 and (bmin + span * .25) <= amt <= (bmin + span * .75)
        rows.append(("금액", 15 if central else 13, 15,
                     f"계약금액 {won(amt)} — 희망 금액대 " + ("중심 구간" if central else "내")))
    elif amt:
        rows.append(("금액", 4, 15, f"계약금액 {won(amt)} — 희망 금액대 밖"))
    else:
        rows.append(("금액", 7, 15, "계약금액 미공개"))

    if d_day <= 90:
        rows.append(("재발주임박", 20, 20, f"만기 D-{d_day} — 재발주 규격 확정 전 접촉 구간"))
    elif d_day <= 180:
        rows.append(("재발주임박", 13, 20, f"만기 D-{d_day} — 준비 착수 적기"))
    else:
        rows.append(("재발주임박", 7, 20, f"만기 D-{d_day} — 모니터링 단계"))

    total = sum(p for _, p, _, _ in rows)
    return total, (rows, warns)


def renewal_actions(r, d_day):
    a = []
    if d_day <= 90:
        a.append("발주기관 담당부서에 현행 시스템 개선 수요 확인 (규격 협의 가능 구간)")
    else:
        a.append("재발주 시점 추적 대상으로 등록 — D-90 진입 시 접촉")
    if r["supplier"]:
        a.append(f"현 수행업체({r['supplier']}) 대비 차별화 요소(단가·유지보수 조건) 준비")
    if r["instt_tel"]:
        a.append(f"계약기관 담당 {r['instt_ofcl'] or ''} {r['instt_tel']}")
    return a


# ------------------------------------------------------------------ html --
CSS = '''body{font-family:"Apple SD Gothic Neo","Malgun Gothic",sans-serif;color:#1b1b1b;
margin:0;background:#fff;font-size:13.5px;line-height:1.6}
.page{max-width:780px;margin:0 auto;padding:0 26px 40px;position:relative;overflow:hidden}
.band{background:#162e51;color:#fff;margin:0 -26px;padding:22px 26px 16px}
.band .t1{font-size:12px;color:#ffbe2e;letter-spacing:.15em;font-weight:700}
.band h1{margin:4px 0 2px;font-size:21px}
.band .sub{font-size:12px;color:#a9aeb6}
.redline{height:4px;background:#b50909;margin:0 -26px}
h2{font-size:14px;border-left:4px solid #162e51;padding-left:8px;margin:26px 0 10px}
.note{border:1px solid #dfe1e2;border-left:4px solid #005ea2;padding:10px 12px;
font-size:12.5px;color:#3d4551;margin:8px 0 14px}
.op{border:1px solid #dfe1e2;border-top:4px solid #162e51;margin-bottom:12px;
display:flex;page-break-inside:avoid}
.op.hot{border-top-color:#b50909}
.sc{flex:0 0 108px;background:#f4f5f6;text-align:center;padding:16px 8px;border-right:1px solid #dfe1e2}
.sc .n{font-size:38px;font-weight:900;color:#b50909;line-height:1}
.sc .n small{font-size:15px;color:#1b1b1b}
.sc .lb{font-size:11px;color:#565c65;margin-top:2px}
.sc .tag{display:inline-block;margin-top:8px;font-size:11px;font-weight:800;padding:2px 8px}
.sc .tag.rec{background:#b50909;color:#fff}
.sc .tag.rev{background:#e6e6e6;color:#3d4551}
.bd{flex:1;padding:12px 14px}
.bd h3{margin:0 0 2px;font-size:14.5px;line-height:1.4}
.bd .mt{font-size:12px;color:#565c65;margin-bottom:8px}
.bd .mt b{color:#1b1b1b}
.ck{margin:0;padding:0;list-style:none;font-size:12.5px}
.ck li{padding:2px 0 2px 22px;position:relative}
.ck li:before{position:absolute;left:0;font-weight:900}
.ck li.ok:before{content:"✓";color:#00695c}
.ck li.warn:before{content:"!";color:#8a3b00}
.ck li.no:before{content:"×";color:#b50909}
.brk{border-collapse:collapse;width:100%;font-size:12px;margin:2px 0 4px}
.brk th{background:none;border:0;text-align:left;color:#565c65;font-weight:700;
padding:3px 8px 3px 0;white-space:nowrap;width:52px}
.brk td{border:0;padding:3px 8px 3px 0;vertical-align:middle}
.brk td.pt{font-weight:900;white-space:nowrap;width:58px;font-variant-numeric:tabular-nums}
.brk td.pt small{color:#8a8f98;font-weight:400}
.brk td.pt.full{color:#00695c}
.brk td.pt.low{color:#b50909}
.brk td.bar{width:90px}
.brk td.bar span{display:block;height:7px;background:#162e51;min-width:2px}
.brk tr:nth-child(1) td.bar span,.brk tr td.bar span{background:#005ea2}
.brk td.why{color:#3d4551}
.act{margin-top:8px;border-top:1px dashed #dfe1e2;padding-top:7px;font-size:12.5px}
.act b{color:#162e51}
.dd{font-weight:800;color:#b50909}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{border:1px solid #dfe1e2;padding:6px 8px;text-align:left}
th{background:#eef1f4;white-space:nowrap}
.foot{border-top:1px solid #dfe1e2;margin-top:30px;padding-top:10px;font-size:11px;color:#565c65}
.wm{position:absolute;top:40%;left:50%;transform:translate(-50%,-50%) rotate(-24deg);
font-size:46px;font-weight:900;color:rgba(181,9,9,.13);white-space:nowrap;pointer-events:none;z-index:9}
@media print{.page{max-width:none}}'''


def card(score, tag, title, meta, rows, warns, actions, hot):
    """rows: (카테고리, 득점, 배점, 근거) — 배점표를 그대로 노출한다."""
    tag_cls = "rec" if tag == "추천" else "rev"
    br = "".join(
        f'<tr><th>{c}</th>'
        f'<td class="pt{" full" if p == m else (" low" if p <= m*0.4 else "")}">{p}<small>/{m}</small></td>'
        f'<td class="bar"><span style="width:{int(p/m*100)}%"></span></td>'
        f'<td class="why">{note}</td></tr>'
        for c, p, m, note in rows)
    wn = "".join(f'<li class="warn">{w}</li>' for w in warns)
    act = " · ".join(actions)
    return (f'<div class="op{" hot" if hot else ""}">'
            f'<div class="sc"><div class="n">{score}<small>점</small></div>'
            f'<div class="lb">수주 적합도</div><div class="tag {tag_cls}">{tag}</div></div>'
            f'<div class="bd"><h3>{title}</h3><div class="mt">{meta}</div>'
            f'<table class="brk">{br}</table>'
            + (f'<ul class="ck">{wn}</ul>' if wn else "")
            + f'<div class="act"><b>권장 조치</b> — {act}</div></div></div>')


def build(a):
    con = sqlite3.connect(ROOT / "data" / "radar.sqlite3")
    con.row_factory = sqlite3.Row
    today = date.today()
    extra = [k.strip() for k in (a.keywords or "").split(",") if k.strip()]
    cust = {
        "industry": "cctv",
        "company": a.company,
        "bizrno": a.bizrno,
        "keywords_include": extra,
        "keywords_exclude": [k.strip() for k in (a.exclude or "").split(",") if k.strip()],
        "regions": [a.region] if a.region else [],
        "licenses": [k.strip() for k in (a.licenses or "").split(",") if k.strip()],
        "budget_min": int(a.min * EOK) if a.min else 0,
        "budget_max": int(a.max * EOK) if a.max else 10**15,
    }

    hist = History(con, cust)

    # ---- 1. 진행 공고 -------------------------------------------------------
    bids = []
    for r in con.execute("SELECT * FROM bid ORDER BY bid_ntce_date DESC LIMIT 8000"):
        s, rows, warns, fail = score_bid_detail(r, cust, today, hist)
        if fail or s is None or s < a.floor:
            continue
        bids.append((s, r, rows, warns))
    bids.sort(key=lambda x: -x[0])

    # ---- 2. 만기 계약 -------------------------------------------------------
    rens = []
    if a.tier in ("standard", "deep"):
        t8 = today.strftime("%Y%m%d")
        for r in con.execute("SELECT * FROM contract WHERE period_end >= ? "
                             "ORDER BY period_end LIMIT 3000", (t8,)):
            dd = days_to(r["period_end"], today)
            if dd is None or dd > 240:
                continue
            s, detail = score_renewal_detail(r, cust, dd, hist)
            if s is None or s < a.floor:
                continue
            rens.append((s, r, detail, dd))
        rens.sort(key=lambda x: (-x[0], x[3]))

    # ---- 3. 낙찰 이력 -------------------------------------------------------
    wins = []
    if a.tier == "deep":
        dic = INDUSTRY_KEYWORDS["cctv"]
        kws = [_norm(k) for k in dic["core"] + dic["adjacent"] + extra]
        for r in con.execute("SELECT * FROM scsbid WHERE winner<>'' ORDER BY opening_date DESC LIMIT 3000"):
            if any(k and k in _norm(r["notice_name"]) for k in kws):
                wins.append(r)

    tier_nm = {"light": "LIGHT", "standard": "STANDARD", "deep": "DEEP"}[a.tier]
    cond = " · ".join(x for x in [
        ("키워드 " + ", ".join(extra)) if extra else "업종사전(CCTV·물리보안)",
        ("지역 " + a.region) if a.region else "",
        (f"금액 {a.min}~{a.max}억" if (a.min or a.max) else "")] if x)

    h = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>D-90 영업기회 선별 리포트 — {a.company}</title><style>', CSS, '</style></head>',
         '<body><div class="page">',
         ('<div class="wm">샘플 리포트 · 예시 데이터</div>' if a.mock else ""),
         f'<div class="band"><div class="t1">D-90 · {tier_nm} REPORT</div>',
         f'<h1>{a.company} 영업기회 선별 리포트</h1>',
         f'<div class="sub">기준일 {today.isoformat()} · 조건: {cond} · 출처: 조달청 나라장터 공공데이터</div></div>',
         '<div class="redline"></div>',
         '<div class="note" style="margin-top:16px"><b>배점 기준 (100점)</b><br>'
         '공고: <b>사업적합 25</b>(키워드·업종) · <b>참가자격 20</b>(면허+지역제한 — 입찰 참가 가능 여부) · '
         '<b>수주실적 25</b>(낙찰 이력 DB에서 귀사의 유사 사업 수주 검색) · <b>발주처 15</b>(해당 기관 수주 이력 / '
         '기존 업체 고착도) · <b>경쟁환경 15</b>(계약방법·재공고 신호)<br>'
         '만기 계약: 사업적합 25 · 발주처관계 20 · 기존 수행업체 분석 20 · 금액 15 · 재발주 임박도 20<br>'
         '모든 항목의 득점과 근거를 건별로 공개합니다. 실적·고착도는 조달청 낙찰 이력 공공데이터에서 '
         '상호·사업자번호로 검색한 결과이며, 점수는 낙찰 확률이 아닌 조건 적합도입니다. <b>75점 이상 = 추천</b>.</div>']

    rec = sum(1 for s, *_ in bids if s >= 75)
    h.append(f"<h2>1. 진행 중 입찰 기회 — 조건 일치 {len(bids)}건 (추천 {rec}건)</h2>")
    if not bids:
        h.append('<div class="note">조건 일치 공고가 없습니다. 키워드 확장을 제안드립니다.</div>')
    for s, r, rows, warns in bids[:a.limit]:
        dd = days_to(r["bid_clse_date"], today)
        meta = (f'<b>{r["dmnd_instt_nm"] or r["ntce_instt_nm"] or "—"}</b>'
                + (f' · 배정예산 <b>{won(r["asign_bdgt_amt"])}</b>' if r["asign_bdgt_amt"] else "")
                + (f' · 마감 <span class="dd">D-{dd}</span> ({d8(r["bid_clse_date"])})' if dd is not None else ""))
        h.append(card(s, "추천" if s >= 75 else "검토", r["bid_ntce_nm"], meta,
                      rows, warns, action_hint(r, s), s >= 75))

    if a.tier in ("standard", "deep"):
        rec2 = sum(1 for s, *_ in rens if s >= 75)
        h.append(f"<h2>2. 계약 만기 — 재계약 영업 기회 {len(rens)}건 (추천 {rec2}건)</h2>")
        h.append('<div class="note">공고를 기다리면 늦습니다. 만기 90일 전은 재발주 규격이 확정되기 전이라 '
                 '담당 기관 접촉이 가능한 마지막 구간입니다.</div>')
        if not rens:
            h.append('<div class="note">240일 내 만기 예정 중 조건 일치 계약이 조회되지 않았습니다.</div>')
        for s, r, (rows, warns), dd in rens[:a.limit]:
            meta = (f'<b>{r["demand_instt"] or r["contract_instt"] or "—"}</b>'
                    + (f' · 현 수행 <b>{r["supplier"]}</b>' if r["supplier"] else "")
                    + (f' · {won(r["amount"])}' if r["amount"] else "")
                    + f' · 만기 <span class="dd">D-{dd}</span> ({d8(r["period_end"])})')
            h.append(card(s, "추천" if s >= 75 else "검토", r["contract_name"], meta,
                          rows, warns, renewal_actions(r, dd), s >= 75))

    if a.tier == "deep":
        h.append(f"<h2>3. 낙찰 이력 — 경쟁 구도 {len(wins)}건</h2>")
        if wins:
            h.append("<table><tr><th>개찰일</th><th>공고명 / 발주기관</th><th>낙찰업체</th><th>낙찰금액</th></tr>")
            for r in wins[:a.limit]:
                h.append(f"<tr><td>{d8(r['opening_date'])}</td>"
                         f"<td>{r['notice_name']}<br><span style='color:#565c65;font-size:11.5px'>"
                         f"{r['demand_instt'] or r['notice_instt'] or ''}</span></td>"
                         f"<td>{r['winner']}</td><td>{won(r['winner_amount'])}</td></tr>")
            h.append("</table>")
        else:
            h.append('<div class="note">낙찰 이력 데이터가 아직 수집되지 않았습니다.</div>')
        h.append("<h2>4. 접근 전략 노트</h2>")
        h.append('<div class="note">① 추천(75+) 공고: 권장 조치의 담당자 연락처부터. '
                 '② 만기 D-90 이내 추천 건: 규격 협의 단계 접촉 — 현 수행업체 대비 차별화 요소 지참. '
                 '③ 낙찰 이력의 반복 수주 업체가 있는 기관: 기존 관계를 감안해 단가·유지보수 조건으로 승부. '
                 '— 본 노트는 데이터 패턴에 대한 일반 가이드이며 개별 입찰 판단의 책임은 입찰자에게 있습니다.</div>')

    h.append('<div class="foot">본 리포트의 모든 수치·일자·업체명은 조달청 나라장터 공공데이터 원문에서 추출했으며, '
             '적합도 점수는 위 명시된 규칙 계산입니다. 언어모델이 생성한 수치나 판단은 포함되지 않습니다. '
             '확정 내용은 나라장터 원문을 기준으로 하십시오.'
             + (" <b>본 문서는 예시 데이터로 만든 샘플입니다.</b>" if a.mock else "") + "</div>")
    h.append("</div></body></html>")

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"D90_{tier_nm}_{'SAMPLE' if a.mock else _norm(a.company)[:12]}_{today:%Y%m%d}.html"
    p.write_text("".join(h), encoding="utf-8")
    print(f"OK  {tier_nm} -> {p}")
    print(f"    공고 {len(bids)}건(추천 {rec}) / 만기 {len(rens)}건 / 낙찰 {len(wins)}건")
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["light", "standard", "deep"], required=True)
    ap.add_argument("--company", default="고객사")
    ap.add_argument("--keywords", default="")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--region", default="")
    ap.add_argument("--licenses", default="")
    ap.add_argument("--bizrno", default="", help="사업자등록번호 — 낙찰 이력 매칭 정확도 향상")
    ap.add_argument("--min", type=float, default=0, help="최소 금액(억)")
    ap.add_argument("--max", type=float, default=0, help="최대 금액(억)")
    ap.add_argument("--floor", type=int, default=55, help="표시 최저 점수")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--mock", action="store_true")
    a = ap.parse_args()
    if a.mock:
        import subprocess, sys
        subprocess.run([sys.executable, str(ROOT / "run_kr.py"), "init"], check=True, capture_output=True)
        subprocess.run([sys.executable, str(ROOT / "run_kr.py"), "seed-mock"], check=True, capture_output=True)
    build(a)


if __name__ == "__main__":
    main()
