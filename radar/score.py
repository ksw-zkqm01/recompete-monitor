"""
룰 기반 수주적합도 스코어링.

원칙: 점수의 모든 근거는 공고 원문 필드에서 나온다. 추정/창작 금지.
      reasons 에 근거를 남기고, 그 문장을 그대로 고객에게 보여준다.
"""
import re
from datetime import date, datetime

WEIGHTS = {
    "keyword": 40,
    "region": 15,
    "budget": 15,
    "license": 15,
    "timing": 15,
}
# 주의: ppsNtceYn 은 '나라장터공고여부'이지 '사전공고여부'가 아니다(공식 명세 확인).
#       초기 구현에서 조기신호 가점으로 잘못 썼던 것을 제거했다.

# 업종 사전 (첫 타깃: CCTV·물리보안)
INDUSTRY_KEYWORDS = {
    "cctv": {
        "core": ["cctv", "씨씨티비", "영상감시", "영상정보처리기기", "방범카메라",
                 "폐쇄회로", "영상보안", "통합관제", "관제센터", "영상관제", "선별관제"],
        "adjacent": ["출입통제", "주차관제", "차량번호인식", "비상벨", "안전마을",
                     "스마트도시안전", "네트워크카메라", "NVR", "DVR",
                     "영상저장장치", "무인단속", "안전관제"],
        "service": ["유지보수", "유지관리", "위탁", "운영", "성능개선", "고도화",
                    "노후교체", "증설", "구축", "설치"],
    }
}


def _norm(s):
    return re.sub(r"\s+", "", (s or "")).lower()


def _parse_date(s):
    s = (s or "").strip().replace("-", "")[:8]
    if len(s) != 8 or not s.isdigit():
        return None
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        return None


def score_bid(bid, cust, today=None):
    """bid: sqlite3.Row 또는 dict / cust: 고객 프로필 dict
    반환: (score:int, reasons:list[str], hard_fail:str|None)"""
    today = today or date.today()
    b = dict(bid)
    g = b.get
    name = g("bid_ntce_nm") or ""
    nname = _norm(name)
    reasons = []

    # ---- 하드 필터 -------------------------------------------------------
    for kw in cust.get("keywords_exclude", []):
        if _norm(kw) and _norm(kw) in nname:
            return 0, [], f"제외키워드 '{kw}' 포함"

    budget = g("asign_bdgt_amt") or g("presmpt_prce") or 0
    bmin = cust.get("budget_min") or 0
    bmax = cust.get("budget_max") or 10**15
    if budget and budget < bmin:
        return 0, [], f"예산 {budget:,}원 < 최소 {bmin:,}원"
    if budget and budget > bmax:
        return 0, [], f"예산 {budget:,}원 > 최대 {bmax:,}원"

    clse = _parse_date(g("bid_clse_date"))
    if clse and clse < today:
        return 0, [], "입찰마감 경과"

    # ---- 1. 키워드 적합도 -------------------------------------------------
    dic = INDUSTRY_KEYWORDS.get(cust.get("industry", "cctv"), INDUSTRY_KEYWORDS["cctv"])
    extra = [k for k in cust.get("keywords_include", [])]
    core_hit = [k for k in dic["core"] + extra if _norm(k) and _norm(k) in nname]
    adj_hit = [k for k in dic["adjacent"] if _norm(k) in nname]
    svc_hit = [k for k in dic["service"] if _norm(k) in nname]

    kw_pts = 0
    if core_hit:
        kw_pts = 40
        reasons.append(f"핵심 키워드 일치: {', '.join(core_hit[:3])}")
    elif adj_hit:
        kw_pts = 26
        reasons.append(f"인접 키워드 일치: {', '.join(adj_hit[:3])}")
    else:
        return 0, [], "업종 키워드 불일치"
    if svc_hit and kw_pts < 40:
        kw_pts = min(40, kw_pts + 6)
    if svc_hit:
        reasons.append(f"사업유형: {', '.join(svc_hit[:2])}")

    # ---- 2. 지역 ---------------------------------------------------------
    rgn_lmt = (g("rgn_lmt_yn") or "N").upper()
    rgn_nm = g("prtcpt_psbl_rgn") or ""
    regions = cust.get("regions", [])
    if rgn_lmt != "Y" or not rgn_nm:
        rg_pts = WEIGHTS["region"]
        reasons.append("지역제한 없음 — 전국 참가 가능")
    else:
        if any(_norm(r) and _norm(r) in _norm(rgn_nm) for r in regions):
            rg_pts = WEIGHTS["region"]
            reasons.append(f"지역제한 '{rgn_nm}' — 영업권역 일치")
        else:
            rg_pts = 0
            reasons.append(f"⚠ 지역제한 '{rgn_nm}' — 영업권역 밖")

    # ---- 3. 예산 ---------------------------------------------------------
    if not budget:
        bd_pts = 7
        reasons.append("예산 미공개")
    else:
        sweet_lo = cust.get("sweet_min") or bmin
        sweet_hi = cust.get("sweet_max") or bmax
        if sweet_lo <= budget <= sweet_hi:
            bd_pts = WEIGHTS["budget"]
            reasons.append(f"배정예산 {budget:,}원 — 주력 사업규모")
        else:
            bd_pts = 8
            reasons.append(f"배정예산 {budget:,}원")

    # ---- 4. 업종제한 / 면허 ----------------------------------------------
    ind_lmt = (g("indstryty_lmt_yn") or "N").upper()
    ind_nm = g("bidprc_indstryty") or ""
    lic = cust.get("licenses", [])
    if ind_lmt != "Y" or not ind_nm:
        lc_pts = WEIGHTS["license"]
        reasons.append("업종제한 없음")
    elif any(_norm(l) and _norm(l) in _norm(ind_nm) for l in lic):
        lc_pts = WEIGHTS["license"]
        reasons.append(f"필요업종 '{ind_nm}' — 보유면허 충족")
    else:
        lc_pts = 0
        reasons.append(f"⚠ 필요업종 '{ind_nm}' — 보유면허 확인 필요")

    # ---- 5. 타이밍 -------------------------------------------------------
    if clse:
        dleft = (clse - today).days
        if dleft >= 7:
            tm_pts = WEIGHTS["timing"]
        elif dleft >= 3:
            tm_pts = 10
        else:
            tm_pts = 4
        reasons.append(f"입찰마감 D-{dleft} ({clse:%Y-%m-%d})")
    else:
        tm_pts = 7

    # ---- 경고 (점수가 아니라 주의사항으로 표시) ---------------------------
    qr = _parse_date(g("qlfct_rgst_clse_date"))
    if qr:
        dq = (qr - today).days
        if dq < 0:
            reasons.append(f"⚠ 입찰참가자격 등록마감 경과 ({qr:%Y-%m-%d}) — 참가 가능 여부 확인 필요")
        elif dq <= 2:
            reasons.append(f"⚠ 입찰참가자격 등록마감 D-{dq} ({qr:%Y-%m-%d})")
    sttus = g("bid_ntce_sttus") or ""
    if "긴급" in sttus:
        reasons.append("긴급공고 — 일정이 짧다")
    if "재공고" in sttus:
        reasons.append("재공고 — 직전 회차 유찰 가능성, 경쟁 낮을 수 있음")
    if (g("presnatn_yn") or "").upper() == "Y":
        pd_ = _parse_date(g("presnatn_date"))
        reasons.append("설명회 실시" + (f" ({pd_:%Y-%m-%d})" if pd_ else ""))

    total = kw_pts + rg_pts + bd_pts + lc_pts + tm_pts
    return min(100, total), reasons, None


def action_hint(bid, score):
    g = dict(bid).get
    hints = []
    if (g("presnatn_yn") or "").upper() == "Y":
        hints.append("제안서 설명회 참석 등록")
    mth = g("cntrct_mthd_nm") or ""
    if "협상" in mth:
        hints.append("협상에 의한 계약 — 제안서 배점 확인")
    if "수의" in mth:
        hints.append("수의계약 — 견적 제출 경로 확인")
    if g("ntce_ofcl_tel"):
        hints.append(f"담당자 {g('ntce_ofcl_nm') or ''} {g('ntce_ofcl_tel')}")
    if not hints:
        hints.append("공고문·규격서 검토 후 참가자격 확인")
    return hints
