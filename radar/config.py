"""
조달청 나라장터 공공데이터개방표준서비스 설정.

근거: 조달청_OpenAPI참고자료_나라장터_공공데이터개방표준서비스_1.2.docx (공식 문서)
      → 아래 필드명·파라미터·조회범위 제한은 전부 공식 명세에서 확인된 값이다.
"""

BASE = "https://apis.data.go.kr/1230000/ao/PubDataOpnStdService"

OPS = {
    "bid": "getDataSetOpnStdBidPblancInfo",
    "scsbid": "getDataSetOpnStdScsbidInfo",
    "contract": "getDataSetOpnStdCntrctInfo",
}

# 공식 명세상 조회범위 제한 (초과하면 결과가 0건으로 나온다)
WINDOW_DAYS = {
    "bid": 30,        # 입찰공고일시 범위 1개월
    "contract": 7,    # 계약체결일자 범위 1주일 (v1.2, 2026.04 축소)
    "scsbid": 1,      # 개찰일시 범위 1일    (v1.2, 2026.06 축소)
}

MAX_TPS = 30          # 초당 최대 트랜잭션

# 업무구분코드 (낙찰정보 조회 시 필수)
BSNS_DIV = {"물품": "1", "외자": "2", "공사": "3", "용역": "5"}

# ---------------------------------------------------------------------------
# 계약정보 응답 → DB 컬럼 매핑 (공식 명세 확인됨)
# ---------------------------------------------------------------------------
CONTRACT_MAP = {
    "contract_no":     "cntrctNo",              # 계약번호
    "unty_no":         "untyCntrctNo",          # 통합계약번호
    "contract_ord":    "cntrctOrd",             # 계약차수
    "contract_name":   "cntrctNm",              # 계약명
    "bsns_div":        "bsnsDivNm",             # 업무구분명
    "concl_mthd":      "cntrctCnclsMthdNm",     # 계약체결방법명
    "lngtrm_div":      "lngtrmCtnuDivNm",       # 장기계속구분명
    "concl_date":      "cntrctCnclsDate",       # 계약체결일자
    "period_raw":      "cntrctPrd",             # 계약기간 (문자열)
    "amount":          "cntrctAmt",             # 계약금액
    "total_amount":    "ttalCntrctAmt",         # 총계약금액
    "contract_instt":  "cntrctInsttNm",         # 계약기관명
    "demand_instt":    "dmndInsttNm",           # 수요기관명
    "instt_ofcl":      "cntrctInsttOfclNm",     # 계약기관담당자명
    "instt_tel":       "cntrctInsttOfclTel",    # 계약기관담당자전화번호
    "supplier":        "rprsntCorpNm",          # 대표업체명  ← 현 수행업체
    "supplier_ceo":    "rprsntCorpCeoNm",       # 대표업체대표자명
    "supplier_bizrno": "rprsntCorpBizrno",      # 대표업체사업자등록번호
    "supplier_addr":   "rprsntCorpAdrs",        # 대표업체주소
    "supplier_tel":    "rprsntCorpContactTel",  # 대표업체연락전화번호
    "bid_notice_no":   "bidNtceNo",
    "contract_url":    "cntrctInfoUrl",
    "bid_url":         "bidNtceUrl",
    "data_bss_date":   "dataBssDate",
}

# ---------------------------------------------------------------------------
# 낙찰정보 응답 → DB 컬럼 매핑 (공식 명세 확인됨)
# 여기에 '최종낙찰업체 + 전화번호'가 들어있다 → 영업 콜 리스트의 원천
# ---------------------------------------------------------------------------
SCSBID_MAP = {
    "bid_notice_no":   "bidNtceNo",
    "bid_notice_ord":  "bidNtceOrd",
    "notice_name":     "bidNtceNm",
    "bsns_div":        "bsnsDivNm",
    "concl_mthd":      "cntrctCnclsMthdNm",
    "winner_mthd":     "bidwinrDcsnMthdNm",
    "notice_instt":    "ntceInsttNm",
    "demand_instt":    "dmndInsttNm",
    "opening_date":    "opengDate",             # 개찰일자
    "opening_result":  "opengRsltDivNm",        # 개찰결과구분명
    "opening_rank":    "opengRank",             # 개찰순위
    "presmpt_prce":    "presmptPrce",           # 추정가격
    "winner":          "fnlSucsfCorpNm",        # 최종낙찰업체명
    "winner_ceo":      "fnlSucsfCorpCeoNm",     # 최종낙찰업체대표자명
    "winner_bizrno":   "fnlSucsfCorpBizrno",    # 최종낙찰업체사업자등록번호
    "winner_addr":     "fnlSucsfCorpAdrs",      # 최종낙찰업체주소
    "winner_tel":      "fnlSucsfCorpContactTel",# 최종낙찰업체연락전화번호
    "winner_amount":   "fnlSucsfAmt",           # 최종낙찰금액
    "winner_rate":     "fnlSucsfRt",            # 최종낙찰율
    "winner_date":     "fnlSucsfDate",          # 최종낙찰일자
    "data_bss_date":   "dataBssDate",
}

# ---------------------------------------------------------------------------
# 주의: ppsNtceYn 은 '나라장터공고여부'다. '사전공고여부'가 아니다.
#       (공식 명세 확인. 초기 구현에서 잘못 해석했던 항목 — 점수에서 제거됨)
# ---------------------------------------------------------------------------
