# -*- coding: utf-8 -*-
"""필드별 변화 등급과 '왜 중요한가 / 지금 무엇을 하나' 문구.

원칙: 문구는 전부 여기에 사전 정의된 템플릿이다. LLM이 지어내지 않는다.
      값(old/new)은 원본 레코드에서 그대로 온다.
"""

# severity, why, actions  — actions 는 체크리스트
US = {
  "estimated_solicitation_release": ("high",
    "The estimated solicitation date moved. The acquisition schedule is still being managed, "
    "which shifts teaming, staffing, pricing and the whole capture calendar.",
    ["Check SAM.gov for a new RFI / RFQ / solicitation and its attachments",
     "Re-book proposal staff and partners against the new date",
     "Refresh incumbent-displacement analysis"]),
  "set_aside": ("high",
    "The set-aside changed. This changes who is allowed to bid at all.",
    ["Confirm whether your company can prime under the new lane",
     "If not, reposition as a subcontractor or teaming partner",
     "Verify your certification (8(a) / WOSB / HUBZone) is still current"]),
  "small_business_program": ("high",
    "The small-business program designation changed. The competitive lane moved.",
    ["Confirm eligibility under the new program", "Revisit the teaming map"]),
  "vehicle": ("high",
    "The contract vehicle changed. Holding that vehicle now decides whether you can compete.",
    ["Confirm whether you hold the new vehicle",
     "If not, engage a vehicle holder for a teaming position",
     "Reprice against the new vehicle's terms"]),
  "naics": ("high",
    "The NAICS code changed. Small-business size standard and the competitor set both change with it.",
    ["Re-check the size standard under the new NAICS",
     "Rebuild the likely competitor list"]),
  "status": ("high",
    "Procurement status changed. Verify whether this is still a follow-on, "
    "and whether a cancellation or bridge contract is in play.",
    ["Confirm follow-on status", "Check for a bridge contract",
     "If cancelled, trace where the requirement or funding moved"]),
  "contract_number": ("high",
    "The referenced contract number changed. The incumbent award may have been replaced or extended.",
    ["Look up the new contract number on USAspending",
     "Confirm recipient and obligated amount"]),
  "incumbent": ("high",
    "The incumbent of record changed.",
    ["Determine whether this is a real change of contractor or a data correction",
     "If real, research the new incumbent's contract terms"]),
  "dollar_range": ("medium",
    "The estimated value band changed. Scope or period of performance may have been adjusted.",
    ["Check for SOW / PWS scope changes", "Revisit pricing strategy"]),
  "future_contract_complete": ("medium",
    "The estimated period-of-performance end moved. The base/option structure may have changed.",
    ["Confirm base and option period structure"]),
  "competition": ("medium",
    "The competition flag changed.",
    ["Check whether this is moving toward sole source"]),
  "component": ("low", "The owning component changed.", ["Confirm the buying organization"]),
  "title": ("low", "The requirement title changed.", ["Check whether scope changed with it"]),
  "published_date": ("low", "The forecast entry was refreshed.",
    ["Read alongside the other field changes"]),
}

KR = {
  "bid_clse_date": ("high",
    "입찰 마감일이 바뀌었습니다. 정정공고나 연기가 발생했다는 뜻입니다.",
    ["공고 원문에서 정정 사유 확인", "서류 제출 일정 재조정",
     "연기 사유가 규격 변경이면 규격서 재검토"]),
  "asign_bdgt_amt": ("high",
    "배정예산이 바뀌었습니다. 사업 범위나 수량이 조정됐을 수 있습니다.",
    ["규격서 변경분 확인", "투찰 가격 전략 재검토"]),
  "bid_ntce_sttus": ("high",
    "공고 상태가 바뀌었습니다. 정정·재공고·취소 여부를 확인해야 합니다.",
    ["취소라면 재공고 시점 추적", "재공고라면 직전 유찰 사유 확인 — 경쟁이 낮을 수 있습니다"]),
  "bidprc_indstryty": ("high",
    "입찰참가가능업종이 바뀌었습니다. 참가 자격 자체가 달라집니다.",
    ["보유 면허로 참가 가능한지 즉시 확인", "불가 시 공동수급 검토"]),
  "prtcpt_psbl_rgn": ("high",
    "참가가능지역이 바뀌었습니다.",
    ["영업권역 포함 여부 확인", "지역 업체와의 공동수급 검토"]),
  "cntrct_mthd_nm": ("high",
    "계약체결방법이 바뀌었습니다. 협상/적격심사/수의 여부에 따라 준비물이 완전히 다릅니다.",
    ["협상이면 제안서 배점표 확인", "적격심사면 실적·경영상태 서류 점검"]),
  "period_end": ("high",
    "계약 종료일 정보가 바뀌었습니다. 재발주 시점이 이동했습니다.",
    ["재발주 예상 시점 재계산", "발주 담당 부서 접촉 시점 조정"]),
  "openg_date": ("medium", "개찰일자가 바뀌었습니다.", ["일정 재확인"]),
  "presnatn_date": ("medium", "설명회 일자가 바뀌었습니다.", ["참석 등록 재확인"]),
  "qlfct_rgst_clse_date": ("medium",
    "입찰참가자격 등록 마감일이 바뀌었습니다.",
    ["등록 완료 여부 즉시 확인"]),
  "presmpt_prce": ("medium", "추정가격이 바뀌었습니다.", ["가격 전략 재검토"]),
  "amount": ("medium", "계약금액이 바뀌었습니다.", ["변경계약 사유 확인"]),
  "supplier": ("high", "수행업체가 바뀌었습니다.", ["신규 수행업체 조건 조사"]),
  "ntce_ofcl_tel": ("low", "담당자 연락처가 바뀌었습니다.", ["담당자 교체 여부 확인"]),
  "title": ("low", "사업명 표기가 바뀌었습니다.", ["범위 변경 동반 여부 확인"]),
}

RULES = {"us": US, "kr": KR}

# NEW / GONE 이벤트 문구
EVENT = {
  "us": {
    "NEW": ("high", "A new requirement appeared in the forecast.",
            ["Confirm follow-on status and the current incumbent",
             "Check SAM.gov for prior Sources Sought or RFI activity",
             "Identify the competitive lane and vehicle"]),
    "GONE": ("high",
             "The entry disappeared from the forecast. It may have been cancelled, "
             "consolidated, or already converted into a solicitation.",
             ["Check SAM.gov for a posted solicitation",
              "If cancelled, trace where the funding moved"]),
  },
  "kr": {
    "NEW": ("high", "새로 등록된 건입니다.",
            ["공고 원문·규격서 검토", "참가자격과 마감일 확인"]),
    "GONE": ("medium", "목록에서 사라졌습니다. 마감·취소 또는 데이터 갱신 지연일 수 있습니다.",
             ["나라장터에서 원문 상태 확인"]),
  },
}

SEVERITY_LABEL = {
  "high":   ("ACTION NOW", "지금 대응"),
  "medium": ("PREPARE", "준비"),
  "low":    ("WATCH", "관찰"),
}
SEVERITY_POINTS = {"high": 30, "medium": 12, "low": 4}


def rule_for(source, field):
    return RULES.get(source, {}).get(field)
