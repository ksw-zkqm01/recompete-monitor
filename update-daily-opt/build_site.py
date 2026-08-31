#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정적 사이트 빌더 — docs/ 폴더에 배포용 HTML + 데이터 JSON을 생성한다.

  py -3.11 build_site.py            US 라이브 수집 + KR DB 변환 → docs/data/*.json
  py -3.11 build_site.py --offline  네트워크 없이 동봉 캐시로 빌드 (테스트용)

GitHub Actions가 매일 이 스크립트를 실행해 docs/를 갱신하면,
GitHub Pages 또는 Firebase Hosting이 그대로 서빙한다. 서버가 없다.
"""
import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from webapp import enrich_us, load_kr, load_us_records  # noqa: E402

DOCS = ROOT / "docs"


def build_us(offline=False):
    if offline:
        src, recs = load_us_records()
    else:
        try:
            from sources import us_dhs
            recs = us_dhs.fetch()
            src = "live"
        except Exception as e:
            print(f"!! 라이브 수집 실패({e}) — 캐시로 대체")
            src, recs = load_us_records()
    return {"source": src, "as_of": date.today().isoformat(),
            "records": enrich_us(recs)}


def build_kr():
    ok, bids, rens = load_kr()
    return {"has_db": ok, "bids": bids, "renewals": rens,
            "as_of": date.today().isoformat()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()

    (DOCS / "data").mkdir(parents=True, exist_ok=True)

    # 1) 페이지: dashboard.html을 정적용으로 변환해 복사
    html = (ROOT / "dashboard.html").read_text(encoding="utf-8")
    html = html.replace('fetch("/api/us"+(refresh?"?refresh=1":""))', 'fetch("data/us.json?v="+Date.now())')
    html = html.replace('fetch("/api/kr")', 'fetch("data/kr.json?v="+Date.now())')
    # 정적 사이트에는 라이브 갱신 버튼 대신 갱신 주기 안내
    html = html.replace(
        '+\'<button id="rf">최신 데이터로 갱신</button>\';\n      $("rf").onclick=function(){this.textContent="갱신 중…";loadUS(true);};',
        '+" · 매일 06:00 KST 자동 갱신";')
    # KR 빈 상태 안내: 로컬 개발용 문구(KR_MENU.bat) → 배포용 문구
    html = html.replace(
        "'<code>KR_MENU.bat</code>에서 <strong>1 BIDS</strong>, <strong>2 CONTRACTS</strong>를 실행한 뒤 이 탭을 다시 여십시오.</div>'",
        "'매일 06:00(KST) 자동 수집이 첫 데이터를 쌓는 중입니다. 다음 자동 갱신 후 다시 확인해 주십시오.</div>'")
    (DOCS / "index.html").write_text(html, encoding="utf-8")

    # 2) 데이터
    us = build_us(offline=a.offline)
    (DOCS / "data" / "us.json").write_text(json.dumps(us, ensure_ascii=False), encoding="utf-8")
    kr = build_kr()
    (DOCS / "data" / "kr.json").write_text(json.dumps(kr, ensure_ascii=False), encoding="utf-8")

    print(f"OK  docs/index.html")
    print(f"OK  docs/data/us.json  {len(us['records'])}건 ({us['source']})")
    print(f"OK  docs/data/kr.json  bids {len(kr['bids'])} / renewals {len(kr['renewals'])} (has_db={kr['has_db']})")


if __name__ == "__main__":
    main()
