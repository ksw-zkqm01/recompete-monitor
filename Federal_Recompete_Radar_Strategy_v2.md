# Federal Recompete Radar
## 미국 연방정부 계약 재입찰(Recompete) 조기탐지 사업전략

- 작성일: 2026-08-27
- 상태: MVP 검증 단계
- 1차 타깃: 미국 연방정부 IT·Cybersecurity GovCon 기업
- 핵심 가설: **공고가 뜬 뒤 찾는 서비스가 아니라, 계약 종료·Forecast·Sources Sought/RFI 신호를 조합해 공고 전에 영업해야 할 계약을 알려주면 돈을 받을 수 있다.**

---

## 1. 사업 한 줄 정의

**Federal Recompete Radar = 미국 연방정부 계약의 만료·후속조달·사전시장조사 신호를 결합해, 특정 GovCon 기업이 지금 영업해야 할 기회를 우선순위로 제공하는 AI Sales Intelligence 서비스**

단순 입찰공고 알림이 아니다.

고객에게 필요한 질문은 이것이다.

> “앞으로 6~18개월 안에 다시 시장에 나올 가능성이 높은 계약 중, 우리 회사가 실제로 따낼 만한 것은 무엇이며 지금 무엇을 해야 하는가?”

---

## 2. 해결하려는 문제

미국 GovCon 업체는 이미 다음 데이터를 각각 찾을 수 있다.

- 과거·현재 계약: USAspending.gov
- Sources Sought / Pre-Solicitation / Solicitation: SAM.gov
- 기관별 향후 조달계획: Procurement Forecast
- 계약업체·금액·NAICS·PSC·Set-aside·POC 등

문제는 데이터가 여러 시스템에 흩어져 있고, 단순 검색으로는 다음을 바로 알기 어렵다는 점이다.

1. 어떤 기존 계약이 곧 후속조달될 가능성이 높은가?
2. 기존 사업자가 누구인가?
3. 기존 계약의 규모는 어느 정도인가?
4. Sources Sought/RFI가 새로 나왔는가?
5. 기관 Forecast에 같은 요구사항이 등장했는가?
6. 고객사의 NAICS, 인증, Contract Vehicle, Deal Size와 맞는가?
7. 지금 Capture/BD를 시작해야 하는가?

우리가 판매할 것은 **데이터가 아니라 “행동 가능한 조기 영업신호”**다.

---

## 3. 초기 타깃

### 1차 Vertical
**Federal IT / Cybersecurity**

초기 탐색 NAICS 후보:

- 541511 — Custom Computer Programming Services
- 541512 — Computer Systems Design Services
- 541513 — Computer Facilities Management Services
- 541519 — Other Computer Related Services
- 518210 — Computing Infrastructure Providers / Data Processing / Hosting

초기 Capability 후보:

- Cybersecurity Operations
- SOC / MDR
- IAM / CIAM / Zero Trust
- Cloud / Hybrid Cloud
- DevSecOps
- Network Security
- IT Managed Services
- Security Engineering

### 왜 이 Vertical부터 시작하는가

- 계약 금액이 커서 영업정보의 경제적 가치가 높다.
- Follow-on/Recompete가 반복된다.
- NAICS/PSC와 요구사항 텍스트 분류가 비교적 명확하다.
- Set-aside, Contract Vehicle, 보안요건 등 업체별 적합도 차이가 크다.
- “공고 전에 움직이는 것”의 가치가 크다.

---

## 4. 고객 Persona

### Primary Customer
미국 Federal IT/Cyber GovCon 중소·중견기업

예상 사용자:

- CEO / Founder
- VP Business Development
- Capture Manager
- Growth Director
- Proposal Director
- Federal Sales Director

### 이상적인 고객 프로필

- 연 매출: 약 $5M~$100M
- Federal 계약 경험 있음
- 1~5명의 BD/Capture 인력
- GovWin 같은 대형 플랫폼은 부담스럽거나 활용도가 낮음
- 특정 NAICS/Set-aside/Vehicle에 집중
- $1M~$100M 규모 계약을 추적

---

## 5. 제품의 핵심 차별화

### 만들지 않을 것

- SAM.gov 복제
- USAspending 검색 UI
- “정부 공고 알림”
- 범용 GovCon 데이터베이스
- GovWin 축소판

### 만들 것

**Personalized Recompete Signal**

예시:

> HIGH-PROBABILITY RECOMPETE — 92/100  
> Agency: DHS / CISA  
> Requirement: Enterprise Engineering & Operations Support  
> Incumbent: Sev1Tech  
> Contract Status: Follow-on  
> Estimated Value: $100M+  
> NAICS: 541512  
> Vehicle: GSA Schedule  
>  
> Why now:
> - Follow-on requirement confirmed
> - Forecast recently updated
> - Solicitation milestone changed
> - Customer capability match: 91%
> - Contract vehicle compatible
>  
> Recommended action:
> - Open capture plan
> - Contact listed POC
> - Review incumbent strengths
> - Identify teaming partner
> - Monitor SAM Sources Sought / solicitation

---

## 6. 데이터 전략

### Source A — USAspending.gov

역할:
**기존 Federal contract의 사실관계와 계약 이력**

확보 대상 필드:

- Award ID / PIID
- Recipient / Incumbent
- Awarding Agency
- Awarding Sub Agency
- Description
- Start Date
- End Date
- Period of Performance Current End Date
- Last Modified Date
- Award Amount
- NAICS
- PSC
- Recipient UEI
- IDV의 경우 Last Date to Order

중요:
USAspending Spending by Award API는 계약의 End Date를 결과 필드로 반환할 수 있다.
다만 현재 공식 검색 필터는 종료일 자체를 직접 범위검색하는 방식보다 action/date-signed/last-modified 중심이다.

따라서 MVP 데이터 파이프라인은:

1. 타깃 NAICS/Agency 범위의 계약을 가져옴
2. End Date / Current End Date 저장
3. 우리 DB에서 6/12/18개월 만료 예정 계약 필터링
4. 매일 Last Modified 기준 업데이트
5. SAM/Forecast와 결합

참고:
- https://api.usaspending.gov/docs/endpoints
- https://github.com/fedspendingtransparency/usaspending-api

---

### Source B — SAM.gov Contract Opportunities API

역할:
**실제 시장조사/조달 개시 신호 감지**

주요 Notice Type:

- Sources Sought
- Pre-Solicitation
- Solicitation
- Combined Synopsis/Solicitation
- Award Notice
- Justification

확보 가능 핵심 필드:

- Notice ID
- Title
- Solicitation Number
- Organization
- Posted Date
- Notice Type
- Set-aside
- Response Deadline
- NAICS
- Classification Code
- Award amount / awardee / award number
- Point of Contact
- Place of Performance
- Attachment resource links

운영 포인트:

- Public API key 필요
- Active notice는 매일 업데이트
- 최대 1,000 records/page
- Posted From / To 날짜가 필수

참고:
- https://open.gsa.gov/api/get-opportunities-public-api/

---

### Source C — Agency Procurement Forecast

역할:
**공고 전 가장 강한 조기신호**

Acquisition.gov은 여러 연방기관의 Procurement Forecast 링크를 제공한다.

예:

- DHS
- DOE
- HHS
- DOJ
- State
- Treasury
- DOT
- VA
- GSA
- NASA
- NSF
- SSA 등

참고:
- https://www.acquisition.gov/procurement-forecasts

---

### Source D — DHS APFS

초기 MVP에서 가장 먼저 붙일 Forecast Source.

실제 공개 레코드에서 확인되는 필드:

- Component
- NAICS
- Competition
- Small Business Set-Aside
- Small Business Program
- Contract Vehicle
- Contract Type
- Contract Status
- Incumbent
- Contract Number
- Anticipated Award Quarter
- Estimated Solicitation Release
- Contract Complete
- Requirements Title
- Description
- Estimated Dollar Range
- Place of Performance
- POC
- Change Log

특히 **Change Log 자체가 중요한 영업신호**다.

예:
- Solicitation Release Date 변경
- NAICS 변경
- Dollar Range 변경
- Contract Status 변경
- POC 변경

이 변화는 단순 정적 DB보다 높은 가치를 가진다.

참고:
- https://apfs-cloud.dhs.gov/forecast/

---

## 7. 1차 검증에서 확인된 실제 기회 예시

### 사례 A — CISA Enterprise Engineering and Operations Support Services (CEEOSS)

- Component: DHS HQ / CISA
- NAICS: 541512
- Competition: YES
- Contract Status: Follow-on
- Incumbent: Sev1Tech
- Contract Number: 70RCSJ25FR0000027
- Vehicle: GSA Schedule
- Estimated Dollar Range: Over $100M
- Requirements: Enterprise IT, hybrid cloud, emerging technology, security/availability
- Forecast가 2026년에 반복 업데이트됨

이 레코드는 우리가 원하는 “후속조달 + incumbent + 규모 + NAICS + vehicle + 일정”이 실제 공개데이터에 존재함을 보여준다.

### 사례 B — USCIS Cyber Security Support Services (C3S) II

- Cyber Security Support Services
- NAICS가 541512 → 541519로 변경된 이력 존재
- Dollar Range가 Over $100M → $50M~$100M로 변경
- Estimated Solicitation Release가 여러 차례 변경
- 8(a) / GSA HACS 관련 acquisition strategy 정보 포함

이 사례는 **Change Detection이 상품가치가 될 수 있음**을 보여준다.

### 사례 C — ICE Customer Identity and Access Management Support

- NAICS: 541512
- Follow-on
- Incumbent: IT Strategies
- Contract Number 공개
- Estimated Dollar Range: $1M~$2M
- IAM / Okta / Microsoft Entra 관련 상세 요구사항
- POC 공개

이는 특정 Cyber capability 고객에게 높은 정밀도의 fit score를 제공할 수 있음을 보여준다.

---

## 8. Recompete Score v0.1

초기에는 AI가 모든 판단을 하게 하지 않는다.
**Rule-based Score + GPT 설명** 구조로 간다.

### Opportunity Signal Score / 100

| Signal | Score |
|---|---:|
| Agency Forecast에서 Follow-on 확인 | +25 |
| Sources Sought / RFI 감지 | +20 |
| 기존 계약 종료 12개월 이내 | +15 |
| 기존 계약 종료 6개월 이내 | +5 추가 |
| 기존 Incumbent 확인 | +5 |
| Solicitation Release 날짜 존재 | +10 |
| Forecast 최근 업데이트 | +5 |
| NAICS/PSC 일치 | +5 |
| Budget/Dollar Range 확인 | +5 |
| Contract Vehicle 확인 | +5 |
| Set-aside 확인 | +5 |

### 별도 Company Fit Score / 100

- NAICS match
- PSC match
- Capability semantic match
- Contract Vehicle eligibility
- Set-aside eligibility
- Deal-size fit
- Geography
- Past performance adjacency
- Agency experience

최종 출력:

**Priority Score = Opportunity Signal × Company Fit**

초기에는 정확도를 위해 두 점수를 분리해서 보여준다.

---

## 9. 핵심 제품 화면

### Dashboard 1 — My Recompetes

사용자가 보는 것은 수천 건의 공고가 아니라:

**“This week: 7 opportunities you should act on.”**

필터:

- Act Now
- Watch
- Too Early
- Low Fit

### Opportunity Detail

1. Opportunity Summary
2. Why It Matters Now
3. Current / Incumbent Contract
4. Forecast Timeline
5. SAM Activity
6. Change History
7. Company Fit
8. Competitive Context
9. Recommended Next Action

### Alert

예:

> 🚨 New Recompete Signal  
> CISA / IAM Support  
> Score: 91  
> Forecast changed 2 days ago.  
> Solicitation moved forward by 45 days.  
> Your company matches the NAICS, vehicle and capability profile.

---

## 10. 수익모델

초기에는 “SaaS 기능 수”가 아니라 **놓치면 안 되는 영업기회**에 가격을 붙인다.

### Validation Pricing

#### Solo — $199/month
- 1 company profile
- 1 vertical
- Weekly curated recompete radar
- Up to 20 tracked opportunities

#### Growth — $499/month
- Daily alerts
- Multiple capabilities
- Change detection
- Fit scoring
- Watchlist

#### Capture Team — $999/month+
- Multiple users
- Multiple agencies / NAICS
- Team pipeline
- Capture brief
- Competitor/incumbent intelligence
- Export/API

초기 5~10개 고객은 SaaS가 아니라 **concierge intelligence service**로 판매해도 된다.

---

## 11. 초기 판매 전략

광고부터 하지 않는다.

### 고객 확보 순서

1. Federal Cyber/IT GovCon 100개 선정
2. 각 회사의 Capability / NAICS / certifications / vehicles 파악
3. 회사별 “무료 3개 Recompete Signal” 제작
4. CEO / VP BD / Capture Manager에게 직접 전달
5. 15분 Demo
6. Paid pilot 전환

### Outreach 메시지의 핵심

나쁜 메시지:

> We built an AI government opportunity platform.

좋은 메시지:

> We found 3 federal cyber contracts that appear likely to recompete in the next 12 months and match your NAICS/capabilities.  
> Two have already shown pre-solicitation signals.  
> Want the brief?

제품을 설명하지 말고 **실제 opportunity**를 먼저 보여준다.

---

## 12. Moat

공공데이터 그 자체는 moat가 아니다.

우리의 moat는 시간이 지나면서 다음으로 형성한다.

1. Contract ↔ Forecast ↔ SAM notice 연결 데이터
2. 동일 requirement의 historical identity resolution
3. Forecast change history
4. Recompete probability model
5. Customer-specific fit model
6. Incumbent / teaming / agency relationship graph
7. 어떤 signal이 실제 solicitation/award로 이어졌는지 학습한 outcome data

즉 장기 경쟁력은:

**Raw Data → Linked Opportunity Graph → Predictive Signal**

이다.

---

## 13. 주요 리스크

### 리스크 1 — End Date ≠ Recompete
옵션 행사, extension, bridge contract 때문에 단순 만료일은 오탐이 많다.

대응:
- Forecast Follow-on
- SAM Sources Sought
- Modification
- Potential End Date
- Last Date to Order
- Change Log
- 기관별 패턴

을 결합한다.

### 리스크 2 — 기존 GovWin / GovTribe 경쟁

대응:
- 전체 GovCon 시장을 하지 않는다.
- Federal Cyber/IT부터 시작
- “검색 플랫폼”이 아니라 “actionable alerts”
- 고객별 fit 기반
- 훨씬 낮은 도입비용

### 리스크 3 — Agency Forecast 포맷 불일치

대응:
1차 MVP는 DHS APFS + USAspending + SAM에 집중.
가치가 검증된 후 기관별 parser를 확장.

### 리스크 4 — 데이터 연결 실패

동일한 사업이 계약번호, solicitation number, forecast title에서 다르게 표기될 수 있다.

대응:
- Contract Number exact match
- Solicitation Number
- NAICS
- Agency/Component
- Title semantic similarity
- Incumbent
- Period
를 조합한 entity-resolution layer 구축.

---

## 14. MVP 범위

### MVP v0 — 데이터 검증

대상:
**DHS Federal Cyber/IT only**

Source:
- USAspending
- DHS APFS
- SAM.gov

결과:
- 향후 조달/후속계약 후보 DB
- incumbent
- contract number
- dollar range
- NAICS
- vehicle
- set-aside
- estimated solicitation date
- POC
- change history

### MVP v1 — Concierge Product

UI 없이 시작 가능.

입력:
- 고객 company profile

출력:
- Weekly Top 5 Recompete Brief
- Email / PDF / Web page

### MVP v2 — Automation

- daily ingest
- entity resolution
- score calculation
- GPT summary
- email alert
- customer dashboard

---

## 15. 기술 아키텍처 초안

```text
USAspending API
      │
      ├── Contract / Award / Incumbent / End Date
      │
DHS APFS
      │
      ├── Forecast / Follow-on / Vehicle / POC / Change Log
      │
SAM.gov API
      │
      ├── Sources Sought / Pre-Sol / Solicitation / Award
      │
      ▼
Normalization Layer
      ▼
Entity Resolution
      ▼
Opportunity Graph
      ▼
Rule-based Recompete Score
      ▼
Company Fit Score
      ▼
GPT Explanation / Action Brief
      ▼
Email / Dashboard / CRM
```

추천 초기 Stack:

- Python
- PostgreSQL / Supabase
- Scheduled job / n8n
- OpenAI API
- Lightweight frontend (Next.js 등)
- 초기에는 이메일 delivery만으로도 충분

---

## 16. GO / NO-GO 기준

### GO

다음이 확인되면 개발 진행:

- DHS Cyber/IT forecast에서 유효한 Follow-on 기회가 지속적으로 발생
- 기존 계약과 forecast를 자동/반자동으로 70% 이상 연결 가능
- SAM signal을 추가해 priority를 구분 가능
- 20개 샘플 중 GovCon 실무자가 5개 이상 “유용하다”고 평가
- 최소 3개 업체가 Paid Pilot 의향 표시

### NO-GO / Pivot

- 데이터 연결률이 40% 미만
- 대부분 공고 직전에만 forecast가 공개됨
- 무료 SAM/USAspending 대비 정보 선행성이 거의 없음
- 고객이 이미 동일 기능을 GovWin/GovTribe에서 충분히 활용
- $199+/month 지불의향 없음

Pivot 후보:
- 특정 agency 전용
- 특정 set-aside 기업 전용
- 특정 contract vehicle 전용
- subcontract / teaming opportunity intelligence

---

## 17. 다음 단계

### Phase 1 — Technical Data Validation

1. USAspending API에서 Federal IT/Cyber contracts 추출 방법 확정
2. `End Date`와 `Period of Performance Current End Date` 품질 확인
3. DHS APFS Forecast 수집
4. Follow-on + Incumbent + Contract Number 포함 레코드 추출
5. USAspending 기존 계약과 APFS Forecast 연결
6. SAM API Notice 연결 로직 정의
7. 20개 실제 Recompete Candidate 생성
8. 오탐/누락 평가

### Phase 2 — Customer Validation

20개 실제 signal을 이용해:
- GovCon 업체 20~30개에 무료 샘플 제공
- interview
- willingness-to-pay 확인
- Paid Pilot 3개 목표

---

## 18. 현재 판단

**잠정 GO — Technical Validation 진행 가치 있음**

이유:

1. USAspending에서 계약 종료·업체·NAICS·PSC 등 기반 데이터 확보 가능
2. SAM.gov가 Sources Sought / Pre-Solicitation / Solicitation 등 조달 진행 신호를 API 제공
3. DHS APFS에는 Follow-on, Incumbent, Contract Number, Estimated Solicitation Release, Dollar Range, Vehicle, POC, Change Log까지 실제 존재
4. 실제 2026년 Cyber/IT forecast에서도 $1M~$100M+ 수준의 후속조달 사례가 확인됨
5. 단순 공고검색이 아니라 **데이터 결합 + 변화탐지 + 고객 적합도**가 제품 차별화 후보가 됨

단, 다음 단계에서 반드시 검증할 것은:

> **“이 데이터를 우리가 자동으로 충분히 연결할 수 있는가?”**

이 질문에 YES가 나와야 진짜 사업으로 넘어간다.

---

## 공식 데이터 출처

- USAspending API  
  https://api.usaspending.gov/docs/endpoints

- USAspending API GitHub / Contracts  
  https://github.com/fedspendingtransparency/usaspending-api

- SAM.gov Contract Opportunities Public API  
  https://open.gsa.gov/api/get-opportunities-public-api/

- Federal Agency Procurement Forecast Index  
  https://www.acquisition.gov/procurement-forecasts

- DHS Acquisition Planning Forecast System  
  https://apfs-cloud.dhs.gov/forecast/


---

# 19. Technical Validation Update — 2026-08-29

## 19.1 검증 결과

### 데이터 접근성: GO

USAspending 공식 API는 현재 인증 없이 사용할 수 있고 `/api/v2/search/spending_by_award/`에서 계약에 대해 다음 필드를 반환할 수 있다.

- Award ID
- Recipient Name
- Start Date
- End Date
- Award Amount
- Description
- Last Modified Date
- NAICS
- PSC

SAM.gov Contract Opportunities Public API는 API Key가 필요하며 Sources Sought, Pre-Solicitation, Solicitation, Combined Synopsis/Solicitation 등을 조회할 수 있다.

DHS APFS의 public forecast에는 실제로 다음이 함께 존재한다.

- Follow-on 여부
- Incumbent
- Current Contract Number
- NAICS
- Contract Vehicle
- Set-aside / Small Business Program
- Estimated Solicitation Release
- Estimated Period of Performance
- Dollar Range
- POC
- Change Log

따라서 **APFS → USAspending → SAM** 연결 파이프라인은 기술적으로 구현 가능하다고 판단한다.

## 19.2 MVP 파이프라인 변경

기존:
USAspending 전수수집 → 만료계약 탐색 → APFS/SAM 보강

변경:
**APFS Follow-on 후보 → USAspending incumbent/current award 검증 → SAM 현재 조달활동 검증**

이유:
DHS APFS가 이미 Follow-on 여부와 기존 Contractor/Contract Number를 제공하므로 초기 MVP에서는 훨씬 정밀하고 비용효율적인 seed source가 된다.

## 19.3 20개 실제 DHS IT/Cyber Follow-on 후보

2026-08 기준 APFS 공개 데이터에서 541511/541512/541519 등 IT 계열 Follow-on 후보 20건을 샘플링했다.

샘플은 별도 파일 `dhs_recompete_sample_20.json`에 저장.

확인된 대표적인 신호:

- CISA CEEOSS — $100M+ / incumbent Sev1Tech
- USCIS C3S Architecture II — incumbent Zen Strategics / $50M~$100M
- USCIS C3S Operations II — incumbent AretecSDB / $50M~$100M
- ICE CIAM — Okta/Microsoft Entra / incumbent IT Strategies
- USCIS IASS3 — 8(a) STARS III / security services
- CBP JFrog — DevSecOps/AppSec/software-supply-chain
- TSA Malware Intelligence Subscription — threat hunting/YARA/API
- DHS Oracle Support — $20M~$50M

## 19.4 가장 중요한 신규 리스크 — 직접 경쟁자

2026-08 경쟁조사에서 **PrimeRFP SCOUT**가 단순 간접경쟁이 아니라 거의 동일한 핵심기능을 이미 제공하고 있음을 확인했다.

현재 공개 포지셔닝:

- expiring federal contracts 18~24개월 사전 탐색
- incumbent identification
- recompete pipeline
- early alerts
- personalized/displacement scoring
- ChatGPT/Claude MCP
- $29/month MCP Explorer
- $90 / 90-day Pilot

HigherGov 역시 Federal forecast, incumbents, award history, alerts 등을 제공한다.

### 결론

**“Recompete Radar” 그 자체를 제품으로 만드는 전략은 NO-GO에 가깝다.**

공공데이터를 재포장하는 것만으로는 차별화와 가격력이 부족하다.

## 19.5 전략 Pivot v0.2 — Capture Trigger Intelligence

새 핵심:

> **계약이 언제 끝나는지를 보여주는 것이 아니라, 기관의 조달계획이 오늘 무엇이 바뀌었고 그 변화가 특정 업체의 capture 전략에 어떤 행동을 요구하는지를 즉시 알려준다.**

추적할 변화:

1. Estimated Solicitation Release 날짜 앞당김/연기
2. Contract Vehicle 변경
3. NAICS 변경
4. Set-aside / Small Business Program 변경
5. Dollar Range 변경
6. Competition YES/NO 변경
7. POC / Contracting Officer 변경
8. Contract Status 변경
9. Forecast가 `No Longer Required` / Cancelled / Bridge로 변경
10. SAM Sources Sought / Pre-Sol 등장
11. SAM solicitation 발행
12. incumbent award modification/option exercise
13. bridge award 발생

출력 예:

> **CAPTURE TRIGGER — ACTION REQUIRED**
>
> USCIS C3S Operations II  
> Estimated solicitation moved: Aug 25 → Sep 1  
> Vehicle / lane: GSA HACS 8(a)  
> Incumbent: AretecSDB  
> Value: $50M–$100M  
>
> Why this matters:
> - solicitation slipped for the fourth time
> - requirement remains 8(a)
> - acquisition window is still open
>
> Recommended next action:
> - verify latest PWS/RFQ availability
> - confirm teaming position
> - contact updated POC
> - refresh competitor/incumbent strategy

## 19.6 차별화 가설

PrimeRFP/HigherGov와 비교해 MVP가 검증해야 할 차이는 다음이다.

### A. Change-first
정적 opportunity page가 아니라 **어제 대비 무엇이 바뀌었는지**가 첫 화면.

### B. Action-first
“정보”가 아니라 **오늘 해야 할 BD/Capture action**을 3개 이하로 제시.

### C. Narrow vertical
DHS Cyber/IT, 이후 CISA/USCIS/ICE처럼 component 단위까지 좁혀 고정밀.

### D. Evidence
AI 판단 근거를 공식 APFS/SAM/USAspending 필드와 change history로 직접 제시.

### E. Delivery
사용자가 플랫폼에 로그인하지 않아도 Email/Slack/Teams로 “변화 발생 시에만” 전달.

## 19.7 GO / NO-GO 기준 업데이트

### Technical GO
- APFS 20개 샘플 정상 수집
- incumbent contract number 존재율 70%+
- USAspending exact match 70%+
- Forecast change history 자동 추출 가능
- SAM title/NAICS 기반 matching Precision 70%+

### Commercial GO
- 10명의 미국 GovCon BD/Capture 실무자에게 실제 Change Brief 제시
- 3명 이상이 “기존 도구와 별도로 받을 가치가 있다”고 응답
- 2명 이상이 $99~$299/month paid pilot 수락

### 즉시 NO-GO
- 사용자가 “PrimeRFP/HigherGov alert와 동일하다”고 평가
- change alert가 실제 행동을 거의 바꾸지 않음
- APFS 밖 기관으로 확장 시 forecast diff 수집 비용이 지나치게 큼

## 19.8 생성된 MVP 파일

- `dhs_recompete_sample_20.json` — 실제 DHS Follow-on 샘플 20건
- `federal_recompete_mvp.py` — APFS/USAspending/SAM 연결 및 rule-score 프로토타입

프로토타입은 `--sample-json`으로 오프라인 검증 가능하며, 라이브 환경에서는 SAM_API_KEY를 추가해 SAM 신호까지 결합하도록 설계했다.
