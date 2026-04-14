# CRM 멀티에이전트 시스템

AI 기반 기관투자자 영업 지원 CRM. Claude 멀티에이전트 파이프라인이 고객 데이터와 영업 노트를 분석하여 페르소나 프로파일링, Next Best Action 추천, 활동 일정을 자동 생성합니다.

---

## 주요 기능

- **멀티에이전트 분석 파이프라인** — Persona → NBA → Activity → QC 순서로 자동 실행, 품질 미달 시 자동 재실행
- **실시간 스트리밍** — SSE(Server-Sent Events)로 분석 진행 상황을 웹에서 실시간 확인
- **영업 노트 관리** — 웹 화면에서 미팅/통화 기록 조회·추가, 추가된 노트는 즉시 분석에 반영
- **멀티 모델 지원** — Claude Opus/Sonnet(Anthropic), Gemma/Llama/DeepSeek(OpenRouter 무료) 중 선택
- **자동 DB 전환** — 로컬은 SQLite, Railway 배포 시 PostgreSQL 자동 전환

---

## 스크린샷

### 고객 대시보드
고객별 등급·AUM·담당자 카드, 분석 완료 현황, 모델 선택

### 고객 상세 페이지
- **영업 노트** — 과거 미팅/통화 기록 아코디언 목록, 새 노트 추가 모달
- **AI 분석 실행** — 실시간 로그 터미널
- **분석 결과 탭** — 페르소나 / NBA 추천 / Activity 일정 / QC 검수

---

## 아키텍처

```
웹 브라우저
    │  SSE / REST API
    ▼
web/app.py (FastAPI)
    │
    ├── GET /api/sales-notes/{id}  ─── 영업 노트 조회
    ├── POST /api/sales-notes      ─── 영업 노트 추가
    └── GET /api/analyze/{id}      ─── 파이프라인 실행 (SSE)
              │
              ▼
        OrchestratorAgent
              │ Claude tool_use
    ┌─────────┼──────────┐
    ▼         ▼          ▼         ▼
PersonaAgent  NBAAgent  ActivityAgent  QCAgent
    │         │          │              │
    └─────────┴──────────┴──────────────┘
                         │
                  src/tools/data_tools.py
                         │
              ┌──────────┴──────────┐
         DB (SQLite/PostgreSQL)   data/*.json
         personas, nba_results    customers.json
         activities, qc_reports   action_plans.json
         sales_notes
```

### 에이전트 역할

| 에이전트 | 역할 | 출력 |
|---|---|---|
| **PersonaAgent** | 고객 성향·관심 섹터·커뮤니케이션 스타일 분석 | 페르소나 프로파일 |
| **NBAAgent** | 즉시/단기/중기 액션 및 금지 행동 추천 | NBA 추천 목록 |
| **ActivityAgent** | NBA 기반 구체적 일정·활동 계획 수립 | Activity 스케줄 |
| **QCAgent** | 세 에이전트 출력의 일관성·완결성 검수 | QC 보고서 (pass/fail) |

---

## 빠른 시작

### 사전 요구사항

- Python 3.11+
- Anthropic API 키 ([console.anthropic.com](https://console.anthropic.com))

### 설치

```bash
git clone https://github.com/fabelian/testCRM_multiagent.git
cd testCRM_multiagent

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 환경 설정

프로젝트 루트에 `.env` 파일 생성:

```env
ANTHROPIC_API_KEY=sk-ant-...

# OpenRouter 무료 모델 사용 시 (선택)
OPENROUTER_API_KEY=sk-or-...
```

### 웹 서버 실행

```bash
uvicorn web.app:app --host 0.0.0.0 --port 8000
```

브라우저에서 `http://localhost:8000` 접속

### CLI 실행

```bash
# 단일 고객 분석
python src/main.py C001

# 커스텀 태스크 지정
python src/main.py C001 --task "반도체 섹터 집중 분석만 수행해주세요"

# 전체 고객 순차 분석
python src/main.py --all
```

---

## 영업 노트 관리

고객 상세 페이지의 **영업 노트** 섹션에서:

1. 기존 노트를 날짜순으로 조회 (아코디언 목록)
2. **새 노트 추가** 버튼 클릭 → 모달 폼 입력
   - 날짜, 작성자, 채널(대면미팅/전화/이메일 등)
   - 제목, 내용
   - 감정 평가, 주요 우려사항, 관심 표현사항
   - 후속 조치 필요 여부
3. 저장 후 **분석 시작** → 새 노트가 자동으로 분석에 반영

초기 실행 시 `data/sales_notes.json`의 데이터가 DB로 자동 이전됩니다.

---

## API 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/api/customers` | 전체 고객 목록 |
| `GET` | `/api/customer/{id}` | 고객 분석 결과 조회 |
| `GET` | `/api/analyze/{id}` | 분석 파이프라인 실행 (SSE) |
| `GET` | `/api/sales-notes/{id}` | 고객별 영업 노트 목록 |
| `POST` | `/api/sales-notes` | 새 영업 노트 추가 |
| `GET` | `/api/models` | 사용 가능 모델 목록 |
| `POST` | `/api/model` | 분석 모델 변경 |

### POST /api/sales-notes 요청 예시

```json
{
  "customer_id": "C001",
  "date": "2026-04-15",
  "author": "김영민",
  "channel": "대면미팅",
  "title": "Q1 포트폴리오 리뷰",
  "content": "미팅 내용...",
  "sentiment": "긍정",
  "key_concerns": ["벤치마크 언더퍼폼"],
  "expressed_interests": ["반도체 심층 분석"],
  "follow_up_required": true
}
```

---

## 프로젝트 구조

```
testCRM_multiagent/
├── data/
│   ├── customers.json        # 고객 기본 정보 (읽기 전용)
│   ├── sales_notes.json      # 영업 노트 초기 데이터 (DB 시드용)
│   └── action_plans.json     # 기존 액션 플랜 (읽기 전용)
├── src/
│   ├── agents/
│   │   ├── base_agent.py     # 공통 Agentic Loop
│   │   ├── orchestrator.py   # 파이프라인 조율
│   │   ├── persona_agent.py
│   │   ├── nba_agent.py
│   │   ├── activity_agent.py
│   │   └── qc_agent.py
│   ├── db/
│   │   └── database.py       # SQLAlchemy 모델 & 엔진
│   ├── tools/
│   │   ├── data_tools.py     # 데이터 액세스 레이어
│   │   └── openrouter_client.py
│   └── main.py               # CLI 진입점
├── web/
│   ├── app.py                # FastAPI 앱 & API 라우트
│   └── templates/
│       ├── index.html        # 고객 대시보드
│       └── customer.html     # 고객 상세 + 영업 노트 + 분석 결과
├── output/                   # 분석 보고서 저장 (.gitignore)
├── crm.db                    # SQLite DB (.gitignore)
├── .env.example
└── requirements.txt
```

---

## 지원 모델

| 모델 | 제공사 | 특징 |
|---|---|---|
| Claude Opus 4.6 | Anthropic | 최고 성능 (기본값) |
| Claude Sonnet 4.6 | Anthropic | 빠른 속도 · 낮은 비용 |
| Gemma 4 26B | OpenRouter (무료) | rate limit 있음 |
| Llama 4 Scout | OpenRouter (무료) | rate limit 있음 |
| DeepSeek V3 | OpenRouter (무료) | rate limit 있음 |
| MiniMax M2.5 | OpenRouter (무료) | rate limit 있음 |

---

## 배포 (Railway)

1. Railway 프로젝트에 이 저장소 연결
2. 환경변수 설정: `ANTHROPIC_API_KEY`, `DATABASE_URL` (PostgreSQL)
3. Start Command: `uvicorn web.app:app --host 0.0.0.0 --port $PORT`

`DATABASE_URL`이 `postgres://`로 시작하면 `postgresql://`로 자동 변환됩니다.

---

## 기술 스택

- **Backend**: FastAPI, SQLAlchemy, Uvicorn
- **AI**: Anthropic Claude API (tool_use), OpenRouter
- **DB**: SQLite (로컬) / PostgreSQL (프로덕션)
- **Frontend**: Bootstrap 5.3, Bootstrap Icons, Vanilla JS (SSE)
- **Config**: python-dotenv
