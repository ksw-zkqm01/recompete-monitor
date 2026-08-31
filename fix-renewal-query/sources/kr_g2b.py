# -*- coding: utf-8 -*-
"""KR 어댑터 — 이미 수집해 둔 나라장터 DB(data/radar.sqlite3)를 표준 레코드로 정규화한다.

수집 자체는 기존 radar 모듈이 계속 담당한다. 여기서는 변환만 한다.
"""
import os
import sqlite3
from pathlib import Path

SOURCE = "kr"
RADAR_DB = Path(__file__).resolve().parent.parent / "data" / "radar.sqlite3"


def _con(path=None):
    env = os.environ.get("KR_DB")
    p = Path(path) if path else (Path(env) if env else RADAR_DB)
    if not p.exists():
        raise FileNotFoundError(
            f"나라장터 수집 DB가 없습니다: {p}\n"
            "  TOOLS.bat 로 먼저 수집하거나, 기존 g2b-radar 폴더의 data/radar.sqlite3 를 복사하세요.")
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    return con


def _won(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return f"{v/100_000_000:.1f}억원".replace(".0억", "억") if v >= 100_000_000 else f"{v:,}원"


def fetch_opportunities(db_path=None, limit=20000) -> list[dict]:
    con = _con(db_path)
    out = []
    for r in con.execute("SELECT * FROM bid ORDER BY bid_ntce_date DESC LIMIT ?", (limit,)):
        out.append({
            "entity_id": f'{r["bid_ntce_no"]}-{r["bid_ntce_ord"]}',
            "title": r["bid_ntce_nm"],
            "org": r["dmnd_instt_nm"] or r["ntce_instt_nm"],
            "bid_ntce_sttus": r["bid_ntce_sttus"],
            "bid_clse_date": r["bid_clse_date"],
            "key_date": r["bid_clse_date"],
            "openg_date": r["openg_date"],
            "qlfct_rgst_clse_date": r["qlfct_rgst_clse_date"],
            "presnatn_date": r["presnatn_date"],
            "asign_bdgt_amt": r["asign_bdgt_amt"],
            "presmpt_prce": r["presmpt_prce"],
            "value": _won(r["asign_bdgt_amt"]),
            "prtcpt_psbl_rgn": r["prtcpt_psbl_rgn"],
            "bidprc_indstryty": r["bidprc_indstryty"],
            "industry": r["bidprc_indstryty"],
            "cntrct_mthd_nm": r["cntrct_mthd_nm"],
            "ntce_ofcl_tel": r["ntce_ofcl_tel"],
            "url": r["bid_ntce_url"],
        })
    con.close()
    return out


def fetch_contracts(db_path=None, limit=50000) -> list[dict]:
    con = _con(db_path)
    out = []
    from datetime import date as _date
    today8 = _date.today().strftime("%Y%m%d")
    for r in con.execute(
            "SELECT * FROM contract WHERE period_end >= ? "
            "ORDER BY period_end LIMIT ?", (today8, limit)):
        out.append({
            "entity_id": f'{r["contract_no"]}-{r["contract_ord"]}',
            "title": r["contract_name"],
            "org": r["demand_instt"] or r["contract_instt"],
            "supplier": r["supplier"],
            "incumbent": r["supplier"],
            "amount": r["amount"],
            "value": _won(r["amount"]),
            "period_end": r["period_end"],
            "end_date": r["period_end"],
            "key_date": r["period_end"],
            "concl_mthd": r["concl_mthd"],
            "url": r["contract_url"] or r["bid_url"],
        })
    con.close()
    return out
