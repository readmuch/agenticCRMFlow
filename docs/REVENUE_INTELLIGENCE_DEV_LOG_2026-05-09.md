# Revenue Intelligence 개발 로그

작성일: 2026-05-09

## 배경

`docs/RevenueIntelligenceDesign.md`의 설계를 현재 `agenticCRMFlow` 구조에 맞춰 1차 MVP로 반영했다.

현재 프로젝트에는 이미 `Persona`, `NBA`, `Activity`, `QC`, `DislikeChecker`, `ChatAgent`가 있으므로 기존 파이프라인을 변경하지 않는 방향을 우선했다. 실제 commission, broker vote, wallet share 데이터가 없을 가능성이 높기 때문에 1차 구현은 실제 매출 귀속이 아니라 `proxy signal` 기반 Revenue Intelligence로 설계했다.

## 1차 반영 사항

### 1. DB 모델 추가

파일: `src/db/database.py`

새 테이블 모델을 추가했다.

```python
class RevenueIntelligence(Base):
    __tablename__ = "revenue_intelligence"
    customer_id = Column(String, primary_key=True)
    data = Column(JSON, nullable=False)
```

기존 프로젝트의 agent output 저장 방식과 동일하게 `customer_id + JSON data` 구조를 사용한다.

### 2. data_tools 저장/조회 헬퍼 추가

파일: `src/tools/data_tools.py`

추가된 주요 함수:

- `save_revenue_intelligence(customer_id, revenue_data)`
- `get_revenue_intelligence(customer_id)`
- `get_all_revenue_intelligence()`
- `update_note_revenue_intelligence(note_id, ri_tags, ri_scores)`

고객 삭제 시 `revenue_intelligence` 레코드도 함께 삭제되도록 `delete_customers()`에 cascade 삭제 로직을 추가했다.

`build_full_context()`에는 `revenue_intelligence`를 포함해 향후 ChatAgent 또는 다른 Agent가 전체 context에서 참조할 수 있도록 했다.

### 3. 신규 RevenueIntelligenceAgent 추가

파일: `src/agents/revenue_intelligence_agent.py`

새 Agent는 기존 `NBAAgent`를 확장하지 않고 독립 Agent로 만들었다. 이유는 다음과 같다.

- NBA는 행동 추천이 주 목적이다.
- Revenue Intelligence는 interaction 가치, service mix, wallet influence proxy 분석이 주 목적이다.
- 두 역할을 섞으면 NBA 출력 JSON과 Activity/QC 연동에 영향이 커진다.
- 1차에서는 기존 `Persona -> NBA -> Activity -> QC` 파이프라인을 유지하는 것이 더 안전하다.

Agent의 주요 역할:

- 최근 3개월 sales notes 로드
- customer, persona, NBA context 참조
- note-level RI tagging 생성
- customer-level Revenue Intelligence 저장
- 실제 매출 데이터가 없음을 전제로 `proxy_mode: true` 유지

주요 출력 구조:

```json
{
  "proxy_mode": true,
  "summary": "...",
  "analysis_date": "YYYY-MM-DD",
  "analysis_window": {"from": "...", "to": "..."},
  "client_scores": {
    "engagement_momentum": 0,
    "wallet_influence_proxy": 0,
    "service_roi_proxy": 0,
    "retention_risk": "medium"
  },
  "service_mix": [],
  "opportunity_signals": [],
  "proxy_attribution": [],
  "note_enrichment": [],
  "limitations": []
}
```

### 4. note-level enrichment 저장

`sales_notes.data`에 아래 optional 필드가 추가될 수 있다.

```json
{
  "ri_tags": {
    "service_types": [],
    "product_tags": [],
    "intent_level": "medium",
    "sentiment": "positive",
    "objection_types": [],
    "decision_stage": "evaluation",
    "requested_followup": true
  },
  "ri_scores": {
    "engagement_score": 0,
    "influence_score": 0,
    "revenue_proxy_score": 0,
    "confidence": 0.0
  },
  "ri_tagged_at": "YYYY-MM-DD HH:MM"
}
```

기존 sales note 렌더링은 모르는 필드를 무시하므로 하위 호환성을 유지한다.

### 5. FastAPI API 추가

파일: `web/app.py`

추가된 API:

- `GET /api/revenue-intelligence/{customer_id}`
- `GET /api/all-revenue-intelligence`
- `GET /api/run/revenue-intelligence/{customer_id}`
- `GET /api/run/revenue-intelligence-all`

단일 실행은 기존 `_agent_sse()` 패턴을 재사용했다.

전체 실행은 `persona-all`, `nba-all`, `activity-all`, `qc-all`과 동일한 SSE progress 구조로 구현했다.

### 6. 고객 상세 UI 추가

파일: `web/templates/customer.html`

Sales Notes 아래, Persona 위에 `Revenue Intelligence` 섹션을 추가했다.

표시 항목:

- Proxy Mode badge
- 분석일
- Retention Risk
- Engagement Momentum
- Wallet Influence Proxy
- Service ROI Proxy
- Service Mix
- Opportunity Signals
- Proxy Attribution
- Limitations

`RI 분석` 버튼으로 단일 고객 Revenue Intelligence를 실행할 수 있다.

분석 완료 후 sales notes를 다시 불러와 note-level `RI score` badge도 표시하도록 했다.

### 7. 전체 대시보드 UI 추가

파일: `web/templates/index.html`

새 탭:

- `Revenue Intelligence`

추가 기능:

- 전체 RI 분석 실행
- SSE progress panel
- 전체 RI 결과 조회
- 고객명/서비스/신호 검색
- 등급 필터
- retention risk 필터
- 고객별 score card 표시

## 1차 MVP에서 의도적으로 제외한 사항

다음은 1차에서는 구현하지 않았다.

- 실제 commission 데이터 업로드
- broker vote 업로드
- wallet share 업로드
- 실제 revenue attribution 계산
- Product ROI 계산
- NBAAgent 우선순위에 RI 점수 반영
- ActivityAgent에 RI signal 직접 연결
- QCAgent의 RI 품질 검수
- ChatAgent의 RI 질의 도구
- proxy weight 설정 UI

## 검증 결과

Python 문법 검증:

```bash
python -m py_compile src/db/database.py src/tools/data_tools.py src/agents/revenue_intelligence_agent.py web/app.py
```

결과: 통과.

추가 import smoke test는 현재 로컬 셸 환경에 `sqlalchemy`가 설치되어 있지 않아 실패했다.

`requirements.txt`에는 아래 의존성이 이미 포함되어 있다.

```text
sqlalchemy>=2.0.0
```

따라서 앱 실행 환경에서는 의존성 설치 후 DB import 및 `init_db()` 확인이 필요하다.

## 2차 반영 예정 사항

### 1. NBAAgent와 선택적 연동

`NBAAgent`의 `load_persona_and_recent_notes` 결과에 `revenue_intelligence`를 optional context로 추가한다.

목표:

- `opportunity_signals`가 있는 액션을 NBA 우선순위 판단에 반영
- `wallet_influence_proxy`가 높은 고객에게 더 구체적인 next best product/action 제안
- 단, RI가 없어도 기존 NBA는 정상 동작해야 함

### 2. ActivityAgent 연동

RI의 `opportunity_signals`를 Activity 생성 근거로 연결한다.

예상 필드:

```json
{
  "linked_revenue_signal": {
    "signal": "...",
    "strength": "high",
    "evidence_note_ids": []
  }
}
```

목표:

- Activity가 단순 NBA 일정이 아니라 revenue opportunity 근거를 함께 보유
- 영업 담당자가 왜 이 활동을 해야 하는지 빠르게 확인 가능

### 3. QCAgent 검수 범위 확장

QC 결과에 `revenue_intelligence_review`를 추가한다.

검수 기준:

- 실제 매출처럼 단정하지 않았는지
- evidence note_id가 충분히 연결되었는지
- proxy score와 opportunity signal이 모순되지 않는지
- red flag 또는 explicit dislike를 무시하지 않았는지

### 4. ChatAgent 도구 추가

추가 후보 tool:

- `get_revenue_intelligence(customer_id)`
- `list_revenue_signals(customer_id)`
- `rank_customers_by_wallet_proxy()`
- `search_revenue_opportunities(query)`

예상 질문:

- "corporate access 수요가 높은 고객은?"
- "wallet influence proxy가 높은 고객 Top 5 보여줘"
- "최근 HBM 관련 revenue opportunity는?"

### 5. proxy weight 설정

현재는 LLM이 프롬프트 기준으로 proxy score를 생성한다.

2차에서는 서버 상수 또는 JSON config로 가중치를 분리할 수 있다.

예상 항목:

- activity type weight
- contact role weight
- positive feedback weight
- follow-up request weight
- red flag penalty
- recency decay

### 6. 실제 outcome 데이터 수용 구조

실제 데이터가 생길 경우를 대비해 별도 테이블 또는 JSON 저장 구조를 추가한다.

후보 테이블:

- `revenue_outcomes`
- `broker_votes`
- `wallet_share_snapshots`

초기 API 후보:

- `POST /api/revenue-outcomes/upload`
- `GET /api/revenue-outcomes/{customer_id}`
- `GET /api/revenue-attribution/{customer_id}`

### 7. approximate attribution 계산

실제 outcome 데이터가 연결되면 interaction별 approximate attribution을 계산한다.

예상 방식:

- outcome 발생일 기준 lookback window 설정
- service type별 기본 attribution weight
- recency weight 반영
- evidence confidence 반영
- red flag penalty 반영

### 8. Product / Service ROI Dashboard

대시보드에 product/service 관점 분석을 추가한다.

예상 뷰:

- service type별 고객 반응
- sector/product tag별 opportunity
- analyst call / corporate access / bespoke research별 proxy ROI
- 고객 segment별 선호 service mix

### 9. 수동 보정 workflow

영업 담당자가 RI 결과를 수정할 수 있는 UI를 추가한다.

보정 대상:

- service type
- product tag
- signal strength
- confidence
- false positive 여부

보정 결과는 향후 prompt context 또는 룰 기반 score calibration에 반영한다.

## 운영 메모

1차 구현은 기존 pipeline에 직접 끼우지 않았다. 따라서 기존 `Persona`, `NBA`, `Activity`, `QC`, `DislikeChecker`, `ChatAgent` 흐름은 그대로 유지된다.

Revenue Intelligence는 독립 실행형 분석 결과로 먼저 쌓고, 충분히 결과 품질을 확인한 뒤 2차에서 NBA와 Activity에 optional하게 연결하는 방향이 안전하다.
