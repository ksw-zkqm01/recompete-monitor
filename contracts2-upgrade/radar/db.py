import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "radar.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS bid (
    bid_ntce_no TEXT NOT NULL, bid_ntce_ord TEXT NOT NULL,
    bid_ntce_nm TEXT, bid_ntce_sttus TEXT, bid_ntce_date TEXT,
    bsns_div_nm TEXT, pps_ntce_yn TEXT,
    ntce_instt_nm TEXT, dmnd_instt_nm TEXT,
    ntce_ofcl_nm TEXT, ntce_ofcl_tel TEXT, ntce_ofcl_email TEXT,
    qlfct_rgst_clse_date TEXT,
    bid_begin_date TEXT, bid_clse_date TEXT, bid_clse_tm TEXT, openg_date TEXT,
    asign_bdgt_amt INTEGER, presmpt_prce INTEGER,
    rgn_lmt_yn TEXT, prtcpt_psbl_rgn TEXT,
    indstryty_lmt_yn TEXT, bidprc_indstryty TEXT,
    cntrct_mthd_nm TEXT, bidwinr_mthd_nm TEXT,
    presnatn_yn TEXT, presnatn_date TEXT,
    bid_ntce_url TEXT, raw TEXT,
    fetched_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (bid_ntce_no, bid_ntce_ord)
);
CREATE INDEX IF NOT EXISTS idx_bid_clse ON bid(bid_clse_date);

CREATE TABLE IF NOT EXISTS contract (
    contract_no TEXT NOT NULL, contract_ord TEXT NOT NULL DEFAULT '00',
    unty_no TEXT, contract_name TEXT, bsns_div TEXT, concl_mthd TEXT,
    lngtrm_div TEXT, concl_date TEXT, period_raw TEXT,
    period_begin TEXT, period_end TEXT,
    amount INTEGER, total_amount INTEGER,
    contract_instt TEXT, demand_instt TEXT, instt_ofcl TEXT, instt_tel TEXT,
    supplier TEXT, supplier_ceo TEXT, supplier_bizrno TEXT,
    supplier_addr TEXT, supplier_tel TEXT,
    bid_notice_no TEXT, contract_url TEXT, bid_url TEXT, data_bss_date TEXT,
    raw TEXT, fetched_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (contract_no, contract_ord)
);
CREATE INDEX IF NOT EXISTS idx_ct_end ON contract(period_end);
CREATE INDEX IF NOT EXISTS idx_ct_sup ON contract(supplier);

CREATE TABLE IF NOT EXISTS scsbid (
    bid_notice_no TEXT NOT NULL, bid_notice_ord TEXT NOT NULL DEFAULT '000',
    winner TEXT NOT NULL DEFAULT '',
    notice_name TEXT, bsns_div TEXT, concl_mthd TEXT, winner_mthd TEXT,
    notice_instt TEXT, demand_instt TEXT,
    opening_date TEXT, opening_result TEXT, opening_rank TEXT,
    presmpt_prce INTEGER,
    winner_ceo TEXT, winner_bizrno TEXT, winner_addr TEXT, winner_tel TEXT,
    winner_amount INTEGER, winner_rate TEXT, winner_date TEXT,
    data_bss_date TEXT, raw TEXT,
    fetched_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (bid_notice_no, bid_notice_ord, winner)
);
CREATE INDEX IF NOT EXISTS idx_sc_win ON scsbid(winner);

CREATE TABLE IF NOT EXISTS sent_log (
    customer_id TEXT NOT NULL, item_key TEXT NOT NULL, kind TEXT NOT NULL,
    score INTEGER, sent_at TEXT DEFAULT (datetime('now','localtime')),
    PRIMARY KEY (customer_id, item_key, kind)
);
"""


def connect(path=None):
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


# --- 정규화 --------------------------------------------------------------
def d8(v):
    """API가 주는 '2025-07-01' / '20250701' 을 전부 'YYYYMMDD' 로 통일."""
    s = re.sub(r"[^0-9]", "", str(v or ""))[:8]
    return s if len(s) == 8 else None


def num(v):
    try:
        return int(float(re.sub(r"[^0-9.\-]", "", str(v or ""))))
    except (TypeError, ValueError):
        return None


DATE_RE = re.compile(r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})")


def parse_period(s):
    """계약기간 문자열에서 시작/종료일을 뽑는다.
    실측 표기 (계약정보서비스, 2026-08-31):
      '2016.05.02 ~ 2016.06.03' -> ('20160502','20160603')
      '2026/12/31'              -> (None, '20261231')   단일 날짜는 종료일 표기
      '~ 2026. 8. 31.'          -> (None, '20260831')
      '계약 후 180일 이내'       -> (None, None)          날짜 아님 - 추정하지 않는다
    """
    txt = str(s or "")
    hits = [f"{y}{int(m):02d}{int(d):02d}" for y, m, d in DATE_RE.findall(txt)]
    if not hits:
        # 구분자 없는 8자리 표기: '20260831', '20260101~20261231'
        for t in re.findall(r"20\d{6}", txt):
            mm, dd = int(t[4:6]), int(t[6:8])
            if 1 <= mm <= 12 and 1 <= dd <= 31:
                hits.append(t)
    if not hits:
        return None, None
    if len(hits) == 1:
        return None, hits[0]
    return hits[0], hits[-1]


# '금차 180일, 총차 365일' / '계약 후 180일 이내' / '계약일로부터 60일'
# → 일수만 주는 표기. 종료일 = 계약체결일 + N일 (원문 필드끼리의 규칙 계산).
DUR_RE = re.compile(r"(?:계약\s*후|계약일로부터|금차)\s*(\d{1,4})\s*일")


def derive_end_from_duration(period_raw, concl_d8):
    if not concl_d8:
        return None
    m = DUR_RE.search(str(period_raw or ""))
    if not m:
        return None
    from datetime import datetime, timedelta
    try:
        d = datetime.strptime(concl_d8, "%Y%m%d") + timedelta(days=int(m.group(1)))
        return d.strftime("%Y%m%d")
    except (ValueError, OverflowError):
        return None


def _map(item, mapping):
    return {k: item.get(v) for k, v in mapping.items()}


# --- upsert --------------------------------------------------------------
BID_COLS = 29


def upsert_bids(con, items):
    rows = []
    for it in items:
        rows.append((
            it.get("bidNtceNo", ""), it.get("bidNtceOrd", "") or "000",
            it.get("bidNtceNm"), it.get("bidNtceSttusNm"), d8(it.get("bidNtceDate")),
            it.get("bsnsDivNm"), it.get("ppsNtceYn"),
            it.get("ntceInsttNm"), it.get("dmndInsttNm"),
            it.get("ntceInsttOfclNm"), it.get("ntceInsttOfclTel"),
            it.get("ntceInsttOfclEmailAdrs"),
            d8(it.get("bidPrtcptQlfctRgstClseDate")),
            d8(it.get("bidBeginDate")), d8(it.get("bidClseDate")),
            it.get("bidClseTm"), d8(it.get("opengDate")),
            num(it.get("asignBdgtAmt")), num(it.get("presmptPrce")),
            it.get("rgnLmtYn"), it.get("prtcptPsblRgnNm"),
            it.get("indstrytyLmtYn"), it.get("bidprcPsblIndstrytyNm"),
            it.get("cntrctCnclsMthdNm"), it.get("bidwinrDcsnMthdNm"),
            it.get("presnatnOprtnYn"), d8(it.get("presnatnOprtnDate")),
            it.get("bidNtceUrl"), json.dumps(it, ensure_ascii=False),
        ))
    con.executemany(
        "INSERT OR REPLACE INTO bid VALUES (" + ",".join(["?"] * BID_COLS)
        + ",datetime('now','localtime'))", rows)
    con.commit()
    return len(rows)


def upsert_contracts(con, items):
    from .config import CONTRACT_MAP
    rows = []
    for it in items:
        m = _map(it, CONTRACT_MAP)
        if not m.get("contract_no"):
            continue
        pb, pe = parse_period(m.get("period_raw"))
        rows.append((
            m["contract_no"], m.get("contract_ord") or "00", m.get("unty_no"),
            m.get("contract_name"), m.get("bsns_div"), m.get("concl_mthd"),
            m.get("lngtrm_div"), d8(m.get("concl_date")), m.get("period_raw"),
            pb, pe, num(m.get("amount")), num(m.get("total_amount")),
            m.get("contract_instt"), m.get("demand_instt"),
            m.get("instt_ofcl"), m.get("instt_tel"),
            m.get("supplier"), m.get("supplier_ceo"), m.get("supplier_bizrno"),
            m.get("supplier_addr"), m.get("supplier_tel"),
            m.get("bid_notice_no"), m.get("contract_url"), m.get("bid_url"),
            d8(m.get("data_bss_date")), json.dumps(it, ensure_ascii=False),
        ))
    con.executemany(
        "INSERT OR REPLACE INTO contract VALUES (" + ",".join(["?"] * 27)
        + ",datetime('now','localtime'))", rows)
    con.commit()
    return len(rows)


def _caret_field(s, entry_idx, field_idx):
    """'[1^a^b],[2^c^d]' 형태의 목록 문자열에서 값을 뽑는다. 없으면 None."""
    s = str(s or "").strip().strip("[]")
    if not s:
        return None
    entries = s.split("],[")
    if entry_idx >= len(entries):
        return None
    parts = entries[entry_idx].split("^")
    v = parts[field_idx].strip() if field_idx < len(parts) else ""
    return v or None


def upsert_contracts2(con, items):
    """계약정보서비스(ao/CntrctInfoService) 응답을 contract 테이블에 적재.
    corpList: [순번^역할^구분^업체명^대표^국가^지분^업체명^?^사업자번호]
    dminsttList: [순번^기관코드^기관명^기관구분^^^]  (라이브 응답으로 확인)"""
    from .config import CONTRACT2_MAP
    rows = []
    for it in items:
        m = _map(it, CONTRACT2_MAP)
        no = m.get("contract_no") or m.get("unty_no")
        if not no:
            continue
        # cntrctCnclsDate 가 빈 응답이 있어 cntrctDate 로 폴백 (라이브 실측 확인)
        concl = d8(m.get("concl_date")) or d8(it.get("cntrctDate"))
        pb, pe = parse_period(m.get("period_raw"))
        if pe is None:
            pe = derive_end_from_duration(m.get("period_raw"), concl)
        rows.append((
            no, "00", m.get("unty_no"),
            m.get("contract_name"), it.get("_bsns_div") or m.get("bsns_div"),
            m.get("concl_mthd"), m.get("lngtrm_div"),
            concl, m.get("period_raw"),
            pb, pe, num(m.get("amount")), num(m.get("total_amount")),
            m.get("contract_instt"),
            _caret_field(it.get("dminsttList"), 0, 2),      # 수요기관명
            m.get("instt_ofcl"), m.get("instt_tel"),
            _caret_field(it.get("corpList"), 0, 3),         # 대표업체명
            _caret_field(it.get("corpList"), 0, 4),         # 대표자명
            _caret_field(it.get("corpList"), 0, 9),         # 사업자번호
            None, None,                                     # 주소/전화: 이 API에 없음
            m.get("bid_notice_no"), m.get("contract_url"), m.get("bid_url"),
            d8(m.get("data_bss_date")), json.dumps(it, ensure_ascii=False),
        ))
    con.executemany(
        "INSERT OR REPLACE INTO contract VALUES (" + ",".join(["?"] * 27)
        + ",datetime('now','localtime'))", rows)
    con.commit()
    return len(rows)


def upsert_scsbids(con, items):
    from .config import SCSBID_MAP
    rows = []
    for it in items:
        m = _map(it, SCSBID_MAP)
        if not m.get("bid_notice_no"):
            continue
        rows.append((
            m["bid_notice_no"], m.get("bid_notice_ord") or "000",
            m.get("winner") or "", m.get("notice_name"), m.get("bsns_div"),
            m.get("concl_mthd"), m.get("winner_mthd"),
            m.get("notice_instt"), m.get("demand_instt"),
            d8(m.get("opening_date")), m.get("opening_result"), m.get("opening_rank"),
            num(m.get("presmpt_prce")),
            m.get("winner_ceo"), m.get("winner_bizrno"), m.get("winner_addr"),
            m.get("winner_tel"), num(m.get("winner_amount")), m.get("winner_rate"),
            d8(m.get("winner_date")), d8(m.get("data_bss_date")),
            json.dumps(it, ensure_ascii=False),
        ))
    con.executemany(
        "INSERT OR REPLACE INTO scsbid VALUES (" + ",".join(["?"] * 22)
        + ",datetime('now','localtime'))", rows)
    con.commit()
    return len(rows)


def already_sent(con, cid, key, kind):
    return con.execute(
        "SELECT 1 FROM sent_log WHERE customer_id=? AND item_key=? AND kind=?",
        (cid, key, kind)).fetchone() is not None


def mark_sent(con, cid, key, kind, score):
    con.execute("INSERT OR REPLACE INTO sent_log(customer_id,item_key,kind,score,sent_at)"
                " VALUES (?,?,?,?,datetime('now','localtime'))", (cid, key, kind, score))
    con.commit()
