#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture Trigger — 로컬 웹 대시보드 (표준 라이브러리만 사용, 설치 불필요)

  실행:  py -3.11 webapp.py        (또는 WEB.bat)
  접속:  http://127.0.0.1:8787

데이터 우선순위:
  US — data/web_us.json(라이브 새로고침 캐시) → data_cache_us.json(동봉 캐시, 2026-08-30 실측)
  KR — data/radar.sqlite3 (KR_MENU로 수집한 나라장터 DB). 없으면 KR 탭에 안내만 표시.

원칙: 화면의 모든 숫자·문장은 원문 필드와 사전 정의 규칙에서만 나온다.
"""
import json
import os
import sqlite3
import sys
import threading
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PORT = 8787
APFS_API = "https://apfs-cloud.dhs.gov/api/forecast/"


# ---------------------------------------------------------------- helpers --
def parse_iso(s):
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def load_us_records():
    """정규화된 US 레코드 목록. (source, records)"""
    live = ROOT / "data" / "web_us.json"
    if live.exists():
        return "live-cache", json.loads(live.read_text(encoding="utf-8"))
    bundled = ROOT / "data_cache_us.json"
    if bundled.exists():
        return "bundled-2026-08-30", json.loads(bundled.read_text(encoding="utf-8"))
    return "none", []


def refresh_us():
    from sources import us_dhs
    recs = us_dhs.fetch()
    p = ROOT / "data" / "web_us.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    return recs


def enrich_us(recs, today=None):
    """지연 일수·재게시 여부·심각도·추천 액션을 서버에서 계산해 붙인다."""
    t = today or date.today()
    out = []
    for r in recs:
        r = dict(r)
        sol = parse_iso(r.get("key_date"))
        r["days_to_sol"] = (sol - t).days if sol else None
        r["slipped"] = bool(sol and (sol - t).days < 0)
        r["republished"] = bool(r.get("previous_published_date"))
        pub = parse_iso(r.get("published_date"))
        r["published_days_ago"] = (t - pub).days if pub else None

        trig, acts = [], []
        if r["republished"]:
            trig.append(f'예보 재게시 {r["previous_published_date"]} → {r["published_date"]}')
            acts.append("SAM.gov에서 직전 게시일 이후 신규 공고 여부 확인")
        if r["slipped"]:
            trig.append(f'예상 공고일 {-r["days_to_sol"]}일 경과 ({r.get("key_date")})')
            acts += ["SAM.gov에서 공고가 이미 나왔는지 확인",
                     "담당 POC에게 조달 일정 관련 구체적 질문 1개로 접촉"]
        elif r["days_to_sol"] is not None and r["days_to_sol"] <= 90:
            trig.append(f'예상 공고 D-{r["days_to_sol"]} ({r.get("key_date")})')
            acts += ["이 윈도우에 제안 인력 예약", "기존 수행업체 대체 분석 갱신"]
        if r.get("vehicle"):
            acts.append(f'{r["vehicle"]} 거래 가능 여부 확인')
        r["triggers"] = trig
        r["actions"] = acts[:4]

        score = 0
        if r["republished"]:
            score += 30
        if r["slipped"]:
            score += 30
        elif r["days_to_sol"] is not None and r["days_to_sol"] <= 90:
            score += 22
        if r.get("published_days_ago") is not None and r["published_days_ago"] <= 14:
            score += 20
        score += min(20, int(r.get("base_score") or 0) // 5)
        r["heat"] = min(100, score)
        out.append(r)
    out.sort(key=lambda x: -x["heat"])
    return out


def load_kr():
    """KR 수집 DB → 카드 목록. DB가 없으면 (False, []).

    기본은 data/radar.sqlite3 (로컬 수집분).
    환경변수 KR_DB 가 있으면 그 파일을 읽는다 — GitHub Actions는
    업종 필터 후 누적한 data/kr_store.sqlite3 를 지정한다."""
    env = os.environ.get("KR_DB")
    p = Path(env) if env else ROOT / "data" / "radar.sqlite3"
    if not p.exists():
        return False, [], []
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    t = date.today()
    bids = []
    try:
        for r in con.execute("SELECT * FROM bid ORDER BY bid_ntce_date DESC LIMIT 500"):
            clse = None
            try:
                clse = datetime.strptime(r["bid_clse_date"], "%Y%m%d").date()
            except (ValueError, TypeError):
                pass
            bids.append({
                "entity_id": f'{r["bid_ntce_no"]}-{r["bid_ntce_ord"]}',
                "title": r["bid_ntce_nm"], "org": r["dmnd_instt_nm"] or r["ntce_instt_nm"],
                "value": r["asign_bdgt_amt"], "region": r["prtcpt_psbl_rgn"],
                "industry": r["bidprc_indstryty"], "method": r["cntrct_mthd_nm"],
                "status": r["bid_ntce_sttus"], "url": r["bid_ntce_url"],
                "close": r["bid_clse_date"],
                "d_close": (clse - t).days if clse else None,
            })
    except sqlite3.OperationalError:
        pass
    rens = []
    try:
        for r in con.execute("SELECT * FROM contract WHERE period_end IS NOT NULL AND period_end<>'' ORDER BY period_end LIMIT 500"):
            end = None
            try:
                end = datetime.strptime(r["period_end"], "%Y%m%d").date()
            except (ValueError, TypeError):
                continue
            d = (end - t).days
            if 0 <= d <= 240:
                rens.append({
                    "entity_id": r["contract_no"], "title": r["contract_name"],
                    "org": r["demand_instt"] or r["contract_instt"],
                    "supplier": r["supplier"], "supplier_tel": r["supplier_tel"],
                    "amount": r["amount"], "end": r["period_end"], "d_day": d,
                    "url": r["contract_url"] or r["bid_url"],
                })
    except sqlite3.OperationalError:
        pass
    con.close()
    return True, bids, rens


# ------------------------------------------------------------------ server --
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 콘솔 소음 제거
        pass

    def _send(self, body, ctype="application/json; charset=utf-8", code=200):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            page = ROOT / "dashboard.html"
            body = page.read_text(encoding="utf-8") if page.exists() else HTML
            self._send(body.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/us":
            if "refresh=1" in self.path:
                try:
                    recs = refresh_us()
                    src = "live"
                except Exception as e:
                    src, recs = f"live 실패: {e}", load_us_records()[1]
            else:
                src, recs = load_us_records()
            self._send({"source": src, "as_of": date.today().isoformat(),
                        "records": enrich_us(recs)})
        elif path == "/api/kr":
            ok, bids, rens = load_kr()
            self._send({"has_db": ok, "bids": bids, "renewals": rens,
                        "as_of": date.today().isoformat()})
        else:
            self._send({"error": "not found"}, code=404)


HTML = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Federal Recompete Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;600;700&family=Noto+Sans+KR:wght@400;500;700&display=swap">
<style>
/* U.S. Web Design System 계열 — 흰 바탕, 남색, 직각, 표 중심 */
:root{
  --navy:#162e51; --blue:#005ea2; --blue-dark:#1a4480;
  --ink:#1b1b1b; --ink-2:#565c65; --ink-3:#71767a;
  --bg:#ffffff; --bg-2:#f0f0f0; --bg-3:#f9f9f7;
  --border:#dfe1e2; --border-2:#a9aeb1;
  --red:#b50909; --red-bg:#f8e1de;
  --gold:#936f38; --gold-bg:#faf3d1;
  --green:#216e1f; --green-bg:#e3f0e3;
}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--ink);
  font-family:"Public Sans","Noto Sans KR","Apple SD Gothic Neo",system-ui,sans-serif;
  font-size:15px;line-height:1.55}
.mono{font-variant-numeric:tabular-nums}
a{color:var(--blue)}

/* 정부 배너 스트립 */
.govbar{background:var(--bg-2);border-bottom:1px solid var(--border);
  font-size:12px;color:var(--ink-2);padding:5px 0}
.gb-in{max-width:1120px;margin:0 auto;padding:0 16px}

/* 헤더 */
.site{background:var(--bg);border-bottom:1px solid var(--border)}
.site-in{max-width:1120px;margin:0 auto;padding:14px 16px 0;display:flex;
  flex-wrap:wrap;align-items:baseline;gap:8px 22px}
.brand{font-size:21px;font-weight:700;color:var(--navy);letter-spacing:-.01em}
.brand small{font-weight:400;color:var(--ink-3);font-size:12.5px;margin-left:8px}
.nav{display:flex;gap:2px;margin-left:auto}
.nav button{border:none;background:none;font-family:inherit;font-size:14px;
  padding:10px 14px 12px;cursor:pointer;color:var(--ink-2);
  border-bottom:3px solid transparent;font-weight:600}
.nav button.on{color:var(--navy);border-bottom-color:var(--blue)}
.nav button:focus-visible{outline:2px solid var(--blue);outline-offset:-2px}

.page{max-width:1120px;margin:0 auto;padding:20px 16px 64px}

/* 요약 행 — 숫자 + 괘선, 카드 아님 */
.sumline{display:flex;flex-wrap:wrap;gap:0;border-top:2px solid var(--navy);
  border-bottom:1px solid var(--border);margin:6px 0 18px}
.sum{flex:1 1 160px;padding:14px 18px 14px 0;border-right:1px solid var(--border)}
.sum:last-child{border-right:none}
.sum + .sum{padding-left:18px}
.sum .v{font-size:30px;font-weight:700;color:var(--navy);line-height:1.1}
.sum .v.warn{color:var(--red)}
.sum .k{font-size:12.5px;color:var(--ink-2);margin-top:3px;line-height:1.45}
.asof{font-size:12px;color:var(--ink-3);margin:0 0 4px}
.asof button{border:none;background:none;color:var(--blue);text-decoration:underline;
  cursor:pointer;font:inherit;padding:0;margin-left:8px}

/* 필터 행 — 실제 폼 컨트롤 */
.controls{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;
  background:var(--bg-3);border:1px solid var(--border);padding:12px 14px;margin:0 0 14px}
.ctl{display:flex;flex-direction:column;gap:3px}
.ctl label{font-size:11.5px;font-weight:600;color:var(--ink-2)}
.ctl select,.ctl input[type=search]{font:inherit;font-size:13.5px;padding:6px 8px;
  border:1px solid var(--border-2);background:var(--bg);color:var(--ink);border-radius:0;min-width:130px}
.ctl input[type=search]{min-width:200px}
.ctl select:focus,.ctl input:focus{outline:2px solid var(--blue);outline-offset:1px}
.ctl.grow{flex:1}
.hits{font-size:12.5px;color:var(--ink-2);margin-left:auto;padding-bottom:7px;white-space:nowrap}

/* 데이터 테이블 */
.tblwrap{overflow-x:auto;border:1px solid var(--border)}
table{border-collapse:collapse;width:100%;min-width:860px;font-size:13.5px}
thead th{background:var(--bg-2);text-align:left;padding:8px 12px;font-size:12px;
  color:var(--ink);border-bottom:2px solid var(--border-2);white-space:nowrap;
  cursor:pointer;user-select:none}
thead th .arr{color:var(--blue);font-size:10px}
tbody td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top}
tbody tr.row{cursor:pointer}
tbody tr.row:hover{background:#eff6fb}
tbody tr.row.open{background:#eff6fb}
td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.t-title{font-weight:600;color:var(--blue);text-decoration:underline;text-underline-offset:2px}
.t-org{color:var(--ink-2);font-size:12.5px;margin-top:1px}
.flag{display:inline-block;font-size:11px;font-weight:700;padding:1.5px 7px;
  white-space:nowrap;margin-right:4px}
.flag.late{background:var(--red-bg);color:var(--red)}
.flag.repub{background:var(--gold-bg);color:var(--gold)}
.flag.soon{background:var(--green-bg);color:var(--green)}

/* 행 확장 상세 */
tr.detail td{background:var(--bg-3);border-bottom:1px solid var(--border-2);padding:16px 18px}
.d-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:760px){.d-grid{grid-template-columns:1fr}}
.d-h{font-size:11.5px;font-weight:700;color:var(--ink-2);text-transform:uppercase;
  letter-spacing:.05em;margin:0 0 7px}
.d-trg{border-left:4px solid var(--red);background:var(--bg);padding:8px 12px;
  margin:0 0 6px;font-size:13px}
.d-kv{font-size:13px;line-height:1.7}
.d-kv b{display:inline-block;min-width:96px;color:var(--ink-2);font-weight:400}
.d-act{font-size:13.5px;margin:0;padding-left:20px}
.d-act li{margin:4px 0}
.d-link{font-size:13px}

/* KR / 공통 */
.notice{border-left:4px solid var(--blue);background:var(--bg-3);
  border:1px solid var(--border);border-left-width:4px;border-left-color:var(--blue);
  padding:14px 16px;font-size:14px}
.notice code{background:var(--bg-2);padding:1px 6px;font-size:13px}
.secttl{font-size:16px;font-weight:700;color:var(--navy);margin:24px 0 8px}
.foot{max-width:1120px;margin:28px auto 0;padding:14px 16px 40px;border-top:1px solid var(--border);
  font-size:12px;color:var(--ink-2);line-height:1.7}
[hidden]{display:none!important}
</style>
</head>
<body>

<div class="govbar"><div class="gb-in" id="srcLabel">데이터 불러오는 중…</div></div>

<div class="site"><div class="site-in">
  <span class="brand">Federal Recompete Monitor<small>DHS 조달예보 변화 추적</small></span>
  <nav class="nav">
    <button class="on" id="tabUS">US · DHS APFS</button>
    <button id="tabKR">KR · 나라장터</button>
  </nav>
</div></div>

<div class="page">

  <div id="viewUS">
    <p class="asof" id="asof"></p>
    <div class="sumline" id="sumline"></div>

    <div class="controls">
      <div class="ctl"><label for="fState">상태</label>
        <select id="fState">
          <option value="all">전체</option>
          <option value="slip">공고예정일 경과</option>
          <option value="repub">최근 재게시</option>
          <option value="soon">90일 내 공고 예정</option>
        </select></div>
      <div class="ctl"><label for="fOrg">기관</label><select id="fOrg"><option value="all">전체</option></select></div>
      <div class="ctl"><label for="fVal">금액대</label>
        <select id="fVal">
          <option value="all">전체</option>
          <option value="big">$50M 이상</option>
          <option value="mid">$5M – $50M</option>
          <option value="small">$5M 미만</option>
        </select></div>
      <div class="ctl grow"><label for="q">검색</label>
        <input id="q" type="search" placeholder="사업명, 수행업체, 계약번호"></div>
      <span class="hits" id="cnt"></span>
    </div>

    <div class="tblwrap">
      <table>
        <thead><tr>
          <th data-s="heat">신호 <span class="arr">▼</span></th>
          <th data-s="title">요구사항 / 기관</th>
          <th data-s="incumbent">현 수행업체</th>
          <th data-s="value">금액대</th>
          <th data-s="sol">예상 공고일</th>
          <th data-s="pub">예보 게시</th>
        </tr></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

  <div id="viewKR" hidden><div id="krBody"></div></div>
</div>

<p class="foot" id="foot"></p>

<script>
(function(){
  var US=[], SORT="heat", DESC=true, OPEN=null;
  var F={state:"all",org:"all",val:"all",q:""};
  function $(id){return document.getElementById(id);}
  function esc(s){var d=document.createElement("div");d.textContent=s==null?"":String(s);return d.innerHTML;}

  function loadUS(refresh){
    fetch("/api/us"+(refresh?"?refresh=1":"")).then(function(r){return r.json();}).then(function(d){
      US=d.records||[];
      $("srcLabel").textContent="공식 출처: DHS Acquisition Planning Forecast System (apfs-cloud.dhs.gov) · 데이터: "+d.source;
      $("asof").innerHTML="기준일 "+d.as_of+" · 추적 대상 "+US.length+"건"
        +'<button id="rf">최신 데이터로 갱신</button>';
      $("rf").onclick=function(){ this.textContent="갱신 중…"; loadUS(true); };
      buildOrg(); renderSum(); render();
      $("foot").textContent="이 화면의 모든 수치는 DHS APFS 공개 레코드의 원문 필드에서 규칙으로 계산됩니다. "
        +"지연 일수 = 예상 공고일(estimated_solicitation_release_date)과 기준일의 차이. "
        +"재게시 = published_date와 previous_published_date가 다른 레코드. "
        +"예보는 계획 정보이며 확정 조달 일정이 아닙니다. 실제 공고 여부는 SAM.gov 기준으로 확인하십시오.";
    });
  }

  function buildOrg(){
    var seen={};
    US.forEach(function(r){ var o=(r.org||"").split("/")[0]; if(o) seen[o]=1; });
    var sel=$("fOrg");
    Object.keys(seen).sort().forEach(function(o){
      var op=document.createElement("option"); op.value=o; op.textContent=o; sel.appendChild(op);
    });
  }

  function renderSum(){
    var n=US.length, slip=0, rep=0, soon=0;
    US.forEach(function(r){
      if(r.slipped) slip++;
      if(r.republished && r.published_days_ago!=null && r.published_days_ago<=14) rep++;
      if(!r.slipped && r.days_to_sol!=null && r.days_to_sol<=90) soon++;
    });
    $("sumline").innerHTML=
      '<div class="sum"><div class="v warn">'+slip+'<span style="font-size:16px;color:var(--ink-2);font-weight:400"> / '+n+'건</span></div><div class="k">예상 공고일 경과 — 규격 미확정 상태로 지연 중</div></div>'
     +'<div class="sum"><div class="v">'+Math.round(100*slip/(n||1))+'%</div><div class="k">지연 비율</div></div>'
     +'<div class="sum"><div class="v">'+rep+'</div><div class="k">최근 14일 내 예보 재게시(변경 발생)</div></div>'
     +'<div class="sum"><div class="v">'+soon+'</div><div class="k">90일 내 공고 예정</div></div>';
  }

  function valBand(v){
    v=v||"";
    if(/(\$50M|100M)/.test(v)) return "big";
    if(/(\$5M|\$10M|\$20M)/.test(v)) return "mid";
    return "small";
  }
  function pass(r){
    if(F.state==="slip"&&!r.slipped) return false;
    if(F.state==="repub"&&!(r.republished&&r.published_days_ago!=null&&r.published_days_ago<=45)) return false;
    if(F.state==="soon"&&!(r.days_to_sol!=null&&r.days_to_sol>=0&&r.days_to_sol<=90)) return false;
    if(F.org!=="all"&&(r.org||"").split("/")[0]!==F.org) return false;
    if(F.val!=="all"&&valBand(r.value)!==F.val) return false;
    if(F.q){var h=((r.title||"")+" "+(r.incumbent||"")+" "+(r.contract_number||"")+" "+(r.org||"")).toLowerCase();
      if(h.indexOf(F.q)<0) return false;}
    return true;
  }
  function keyOf(r){
    if(SORT==="heat") return r.heat||0;
    if(SORT==="title") return (r.title||"").toLowerCase();
    if(SORT==="incumbent") return (r.incumbent||"").toLowerCase();
    if(SORT==="value") return r.value||"";
    if(SORT==="sol") return r.key_date||"9999";
    if(SORT==="pub") return r.published_date||"";
    return 0;
  }

  function flags(r){
    var h="";
    if(r.slipped) h+='<span class="flag late">'+(-r.days_to_sol)+'일 경과</span>';
    else if(r.days_to_sol!=null&&r.days_to_sol<=90) h+='<span class="flag soon">D-'+r.days_to_sol+'</span>';
    if(r.republished) h+='<span class="flag repub">재게시</span>';
    return h;
  }

  function render(){
    var rows=US.filter(pass);
    rows.sort(function(a,b){var x=keyOf(a),y=keyOf(b);
      return (x<y?-1:x>y?1:0)*(DESC?-1:1);});
    $("cnt").textContent=rows.length+"건 표시 / 전체 "+US.length+"건";
    var tb=$("tbody"); tb.innerHTML="";
    rows.forEach(function(r){
      var tr=document.createElement("tr");
      tr.className="row"; tr.tabIndex=0; tr.dataset.id=r.entity_id;
      tr.innerHTML='<td class="num mono"><strong>'+r.heat+'</strong></td>'
        +'<td><span class="t-title">'+esc(r.title)+'</span>'
        +'<div class="t-org">'+esc(r.org||"")+' · '+esc(r.entity_id)+'</div>'
        +'<div style="margin-top:4px">'+flags(r)+'</div></td>'
        +'<td>'+esc(r.incumbent||"—")+'</td>'
        +'<td class="num">'+esc(r.value||"—")+'</td>'
        +'<td class="num">'+esc(r.key_date||"—")+'</td>'
        +'<td class="num">'+esc(r.published_date||"—")+'</td>';
      tb.appendChild(tr);
      if(OPEN===r.entity_id){
        var dt=document.createElement("tr"); dt.className="detail";
        dt.innerHTML='<td colspan="6">'+detail(r)+'</td>';
        tb.appendChild(dt); tr.classList.add("open");
      }
    });
    if(!rows.length) tb.innerHTML='<tr><td colspan="6" style="padding:24px;color:var(--ink-2)">조건에 맞는 레코드가 없습니다.</td></tr>';
  }

  function detail(r){
    var trg=r.triggers.length
      ? r.triggers.map(function(t){return '<div class="d-trg">'+esc(t)+'</div>';}).join("")
      : '<div style="font-size:13px;color:var(--ink-2)">특이 신호 없음 — 정기 추적 대상</div>';
    var kv=[["현 계약번호",r.contract_number],["비히클",r.vehicle],["NAICS",r.industry],
            ["구분",r.lane],["이행 종료",r.end_date],["직전 게시",r.previous_published_date],
            ["담당 POC",r.poc_name],["POC 이메일",r.poc_email]]
      .filter(function(x){return x[1];})
      .map(function(x){return "<b>"+esc(x[0])+"</b> "+esc(x[1]);}).join("<br>");
    return '<div class="d-grid"><div>'
      +'<p class="d-h">변화 신호</p>'+trg
      +'<p class="d-h" style="margin-top:14px">권장 조치</p>'
      +'<ol class="d-act">'+r.actions.map(function(a){return "<li>"+esc(a)+"</li>";}).join("")+'</ol>'
      +'</div><div>'
      +'<p class="d-h">레코드 상세</p><div class="d-kv">'+kv+'</div>'
      +(r.url?'<p style="margin-top:12px" class="d-link"><a href="'+esc(r.url)+'" target="_blank" rel="noopener">APFS 원본 레코드 보기</a></p>':"")
      +'</div></div>';
  }

  $("tbody").addEventListener("click",function(e){
    var tr=e.target.closest("tr.row"); if(!tr) return;
    OPEN = OPEN===tr.dataset.id ? null : tr.dataset.id; render();
  });
  $("tbody").addEventListener("keydown",function(e){
    if(e.key!=="Enter") return;
    var tr=e.target.closest("tr.row"); if(!tr) return;
    OPEN = OPEN===tr.dataset.id ? null : tr.dataset.id; render();
  });
  document.querySelectorAll("thead th").forEach(function(th){
    th.addEventListener("click",function(){
      var s=th.dataset.s; if(!s) return;
      if(SORT===s) DESC=!DESC; else {SORT=s; DESC=(s==="heat");}
      document.querySelectorAll("thead .arr").forEach(function(a){a.remove();});
      th.insertAdjacentHTML("beforeend",' <span class="arr">'+(DESC?"▼":"▲")+"</span>");
      render();
    });
  });
  $("fState").onchange=function(){F.state=this.value;render();};
  $("fOrg").onchange=function(){F.org=this.value;render();};
  $("fVal").onchange=function(){F.val=this.value;render();};
  $("q").oninput=function(){F.q=this.value.trim().toLowerCase();render();};

  /* ---- KR ---- */
  function loadKR(){
    fetch("/api/kr").then(function(r){return r.json();}).then(function(d){
      if(!d.has_db||(!d.bids.length&&!d.renewals.length)){
        $("krBody").innerHTML='<div class="notice">나라장터 수집 데이터가 아직 없습니다. '
          +'<code>KR_MENU.bat</code>에서 <strong>1 BIDS</strong>, <strong>2 CONTRACTS</strong>를 실행한 뒤 이 탭을 다시 여십시오.</div>';
        return;
      }
      var h="";
      if(d.renewals.length){
        h+='<p class="secttl">계약 종료 임박 — 재발주 예상 '+d.renewals.length+'건</p>'
          +'<div class="tblwrap"><table><thead><tr><th>D-일</th><th>계약명 / 발주기관</th><th>현 수행업체</th><th style="text-align:right">직전 계약금액</th><th>종료일</th></tr></thead><tbody>'
          +d.renewals.map(function(r){
            var e=r.end||""; e=e.length===8?e.slice(0,4)+"-"+e.slice(4,6)+"-"+e.slice(6):e;
            return "<tr><td class='num'><strong style='color:var(--green)'>D-"+r.d_day+"</strong></td>"
              +"<td><span class='t-title'>"+esc(r.title)+"</span><div class='t-org'>"+esc(r.org||"")+"</div></td>"
              +"<td>"+esc(r.supplier||"—")+"</td>"
              +"<td class='num'>"+(r.amount?Number(r.amount).toLocaleString()+"원":"—")+"</td>"
              +"<td class='num'>"+e+"</td></tr>";
          }).join("")+"</tbody></table></div>";
      }
      if(d.bids.length){
        var live=d.bids.filter(function(b){return b.d_close==null||b.d_close>=0;});
        h+='<p class="secttl">진행 중 공고 '+live.length+'건</p>'
          +'<div class="tblwrap"><table><thead><tr><th>마감</th><th>공고명 / 수요기관</th><th style="text-align:right">배정예산</th><th>지역제한</th><th>상태</th></tr></thead><tbody>'
          +live.slice(0,80).map(function(b){
            return "<tr><td class='num'>"+(b.d_close!=null?"D-"+b.d_close:"—")+"</td>"
              +"<td><span class='t-title'>"+esc(b.title)+"</span><div class='t-org'>"+esc(b.org||"")+"</div></td>"
              +"<td class='num'>"+(b.value?Number(b.value).toLocaleString()+"원":"—")+"</td>"
              +"<td>"+esc(b.region||"없음")+"</td>"
              +"<td>"+(b.status&&b.status.indexOf("정정")>=0?'<span class="flag repub">'+esc(b.status)+"</span>":esc(b.status||"—"))+"</td></tr>";
          }).join("")+"</tbody></table></div>";
      }
      $("krBody").innerHTML=h;
    });
  }

  $("tabUS").onclick=function(){swap(true);};
  $("tabKR").onclick=function(){swap(false);};
  function swap(us){
    $("tabUS").classList.toggle("on",us); $("tabKR").classList.toggle("on",!us);
    $("viewUS").hidden=!us; $("viewKR").hidden=us;
    if(!us) loadKR();
  }

  loadUS(false);
})();
</script>
</body>
</html>"""


def main():
    srv = HTTPServer(("127.0.0.1", PORT), H)
    url = f"http://127.0.0.1:{PORT}"
    print("=" * 52)
    print("  CAPTURE TRIGGER — local dashboard")
    print(f"  {url}")
    print("  Ctrl+C 로 종료")
    print("=" * 52)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
