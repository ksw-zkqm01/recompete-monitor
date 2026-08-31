import os
import time
from datetime import date, timedelta
from urllib.parse import unquote

import requests

from .config import BASE, OPS, WINDOW_DAYS

TIMEOUT = 25
RETRIES = 3
SLEEP = 0.15          # 공식 명세 30 tps. 여유 있게.


class G2BError(RuntimeError):
    pass


def _chunks(bgn: date, end: date, days: int):
    """조회범위 제한(1개월/1주/1일)에 맞춰 기간을 잘라준다."""
    cur = bgn
    while cur <= end:
        last = min(cur + timedelta(days=days - 1), end)
        yield cur, last
        cur = last + timedelta(days=1)


class G2BClient:
    def __init__(self, service_key=None, base=BASE):
        raw = (service_key or os.getenv("DATA_GO_KR_KEY") or "").strip().strip('"').strip("'")
        if not raw:
            raise G2BError("DATA_GO_KR_KEY 없음. SETKEY.bat 을 실행하세요.")
        # Encoding 키(%2B, %3D 등이 섞인 값)를 넣어도 동작하도록 한 번 디코딩한다.
        # requests 가 params 로 다시 인코딩하므로 여기서 풀어두지 않으면 이중 인코딩된다.
        self.key = unquote(raw) if "%" in raw else raw
        self.base = base
        self.s = requests.Session()

    # --- 저수준 -----------------------------------------------------------
    def _get(self, op, params):
        url = f"{self.base}/{op}"
        q = {"ServiceKey": self.key, "type": "json", **params}
        last = None
        for i in range(RETRIES):
            try:
                r = self.s.get(url, params=q, timeout=TIMEOUT)
                txt = r.text.lstrip()
                if "SERVICE_KEY_IS_NOT_REGISTERED" in txt or "SERVICE ERROR" in txt.upper():
                    raise G2BError(
                        "인증키가 등록되지 않았습니다.\n"
                        "  1) data.go.kr 마이페이지 > 오픈API > 개발계정 에서\n"
                        "     '일반 인증키'의 [Decoding] 값을 복사하세요 (%가 없는 값).\n"
                        "  2) SETKEY.bat 을 다시 실행해 붙여넣으세요.\n"
                        "  3) 방금 재발급했다면 활성화까지 최대 1시간 걸릴 수 있습니다.")
                if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in txt:
                    raise G2BError("일일 호출 한도 초과. 마이페이지에서 운영계정 전환을 신청하세요.")
                if txt.startswith("<"):
                    raise G2BError(f"XML 오류 응답: {txt[:300]}")
                if r.status_code != 200:
                    last = f"HTTP {r.status_code}: {r.text[:200]}"
                    time.sleep(1.5 * (i + 1)); continue
                return r.json()
            except requests.RequestException as e:
                last = str(e)
                time.sleep(1.5 * (i + 1))
        raise G2BError(f"{op} 실패: {last}")

    @staticmethod
    def _items(payload):
        body = (payload or {}).get("response", {}).get("body", {}) or {}
        items = body.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        try:
            total = int(body.get("totalCount", 0) or 0)
        except (TypeError, ValueError):
            total = 0
        return items or [], total

    def paged(self, op_key, params, num_rows=999, max_pages=2000):
        op = OPS[op_key]
        page = 1
        while page <= max_pages:
            items, total = self._items(
                self._get(op, {**params, "numOfRows": num_rows, "pageNo": page}))
            if not items:
                return
            for it in items:
                yield it
            if page * num_rows >= total:
                return
            page += 1
            time.sleep(SLEEP)

    # --- 오퍼레이션별 (조회범위 제한 자동 분할) ----------------------------
    def bids(self, bgn: date, end: date, **kw):
        for a, b in _chunks(bgn, end, WINDOW_DAYS["bid"]):
            yield from self.paged("bid", {
                "bidNtceBgnDt": a.strftime("%Y%m%d0000"),
                "bidNtceEndDt": b.strftime("%Y%m%d2359")}, **kw)

    def contracts(self, bgn: date, end: date, **kw):
        for a, b in _chunks(bgn, end, WINDOW_DAYS["contract"]):
            yield from self.paged("contract", {
                "cntrctCnclsBgnDate": a.strftime("%Y%m%d"),
                "cntrctCnclsEndDate": b.strftime("%Y%m%d")}, **kw)

    def scsbids(self, bgn: date, end: date, bsns_div_cds=("1", "5"), **kw):
        """낙찰정보는 개찰일시 1일 + 업무구분코드 필수 → 날짜×구분 이중 루프."""
        for a, b in _chunks(bgn, end, WINDOW_DAYS["scsbid"]):
            for cd in bsns_div_cds:
                yield from self.paged("scsbid", {
                    "bsnsDivCd": cd,
                    "opengBgnDt": a.strftime("%Y%m%d0000"),
                    "opengEndDt": b.strftime("%Y%m%d2359")}, **kw)

    def probe(self, op_key, params, n=1):
        items, total = self._items(self._get(OPS[op_key], {**params, "numOfRows": n, "pageNo": 1}))
        return (items[0] if items else {}), total
