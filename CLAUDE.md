# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 웹 서버 실행 (개발, 자동 리로드)
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload

# 웹 서버 실행 (프로덕션)
uvicorn web.app:app --host 0.0.0.0 --port 8000
# Railway: Start Command는 uvicorn web.app:app --host 0.0.0.0 --port $PORT

# CLI: 단일 고객 분석
python src/main.py C001

# CLI: 커스텀 태스크 지정
python src/main.py C001 --task "반도체 섹터 집중 분석만 수행해주세요"

# CLI: 전체 고객 순차 분석
python src/main.py --all
```

## Environment

`.env` 파일을 프로젝트 루트에 생성 후 실행:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...   # OpenRouter 모델 사용 시 (선택)
DATABASE_URL=postgresql://...  # Railway 배포 시 (로컬은 SQLite 자동 사용)
```

- 웹 앱은 `load_dotenv(override=False)`로 로드 — Railway 등 환경변수가 `.env`보다 우선.
- CLI(`src/main.py:15`)는 `override=True` — `.env` 값이 shell 환경변수를 덮어씀.
- `DATABASE_URL`이 `postgres://`로 시작하면 SQLAlchemy용 `postgresql://`로 자동 치환(`src/db/database.py:18`).

## Architecture

### 멀티에이전트 파이프라인

```
main.py / web/app.py → OrchestratorAgent → PersonaAgent → NBAAgent → ActivityAgent → QCAgent
                                          ↘  DislikeCheckerAgent (노트 red-flag 판정, 독립 호출)
                                          ↘  ChatAgent (대시보드 사이드바, 읽기 전용 tool)
```

Orchestrator는 각 하위 에이전트를 **Claude tool_use** 패턴으로 등록하여 LLM이 실행 순서를 자율 결정합니다. 표준 순서는 Persona → NBA → Activity → QC이며, QC가 fail을 반환하면 문제 에이전트를 최대 1회 재실행합니다. DislikeCheckerAgent와 ChatAgent는 Orchestrator 파이프라인 밖에서 각각 `/api/sales-notes/check-dislikes`, `/api/chat`에서 독립 호출됩니다.

### BaseAgent (`src/agents/base_agent.py`)

모든 에이전트의 공통 Agentic Loop 구현. 핵심 동작:

- **이중 provider 루프**: `provider="anthropic"`는 Anthropic SDK tool_use, `provider="openrouter"`는 OpenAI 호환 function calling. 하위 클래스는 `execute_tool()` 하나만 구현.
- `max_tokens=16000`, `stop_reason == "max_tokens"` 또는 `finish_reason == "length"` 시 최대 5회까지 자동 continuation 요청.
- `stop_reason == "end_turn"` / `finish_reason == "stop"` 시 루프 종료.
- `max_tool_iterations` 파라미터로 도구 호출 반복 상한(무한 루프 방지). ChatAgent는 10으로 제한.
- **OpenRouter 가드**(`base_agent.py:200-214`): HTTP 200 + 빈 `choices` 케이스를 명시적 `RuntimeError`로 변환 (OpenAI SDK가 이를 예외로 전환하지 않음).
- 429 rate limit 시 지수 백오프 재시도 (5s → 10s → 20s → 40s).

### 데이터 레이어 (`src/tools/data_tools.py`)

모든 데이터 읽기/쓰기를 담당하는 순수 함수 모음. 에이전트는 직접 파일·DB 접근 없이 이 모듈만 사용.

**데이터 소스**
- 정적 JSON(읽기 전용): `data/customers.json`, `data/action_plans.json`
- DB 시드 후 영속: `customers`, `sales_notes`, `personas` (각각 `seed_*_if_empty` 함수 존재)
- 에이전트 출력: `personas`, `nba_results`, `activities`, `qc_reports` 테이블

**중요 패턴**
- **KST 타임스탬프**: `now_kst_str()`가 `Asia/Seoul` 고정 오프셋(+9) 분 단위 문자열 반환. 모든 `save_*`가 저장 시 `updated_at`/`generated_at`/`reviewed_at` 자동 주입.
- **Activity envelope**: `save_activities`는 `{activities: [...], updated_at}` 래퍼로 저장하고 `_unwrap_activities`가 레거시 리스트 스키마도 수용. DB에 남은 옛 데이터를 깨지 않기 위함.
- **`since_date` 증분 필터**: `get_recent_notes_with_weights` / `get_customer_feedback_only`가 `since_date` 인자 수용. Persona/NBA 단독 실행(`/api/run/persona/{id}`)은 저장된 `updated_at`/`generated_at`을 컷오프로 재사용해 증분 업데이트. `force=true`면 None으로 전달.
- **Red-flag 메타**: DislikeCheckerAgent 결과를 노트에 영속(`_red_flag`, `_red_flag_matched`, `_red_flag_reason`, `_red_flag_checked_at`). 추가 LLM 호출 없이 프론트·`/api/all-nba`가 재사용.
- **컨텍스트 헬퍼**: `build_raw_context(cid)` = 고객 기본 + 노트 + 액션플랜 (Persona/NBA 입력), `build_full_context(cid)` = 에이전트 결과까지 (QC 입력).
- **전체 조회 헬퍼**: `get_all_customers/personas/nba/activities/qc_reports/sales_notes` — 프론트 전체 조회 탭 백본.

### DB 모델 (`src/db/database.py`)

SQLite(로컬, `crm.db`) / PostgreSQL(Railway) 자동 전환. 6개 테이블 모두 `data JSON` 컬럼에 payload를 담는 동일 구조.

| 테이블 | 모델 클래스 | PK | 설명 |
|---|---|---|---|
| `customers` | `Customer` | `customer_id` | 고객 기본 정보 (JSON 시드 → DB upsert) |
| `personas` | `Persona` | `customer_id` | 고객 페르소나 |
| `nba_results` | `NBAResult` | `customer_id` | NBA 추천 결과 |
| `activities` | `ActivitySchedule` | `customer_id` | Activity 일정 (envelope) |
| `qc_reports` | `QCReport` | `customer_id` | QC 검수 보고서 |
| `sales_notes` | `SalesNote` | `note_id` | 영업 노트 (웹 CRUD, red-flag 메타 포함) |

`web/app.py`의 `lifespan`은 Railway(`DATABASE_URL` 있을 때)에선 **psycopg2로 직접 customers upsert**(`app.py:82-113`)를 수행하고, 로컬 SQLite에선 `seed_customers_if_empty`를 호출.

### 에이전트별 역할

실제 기본 모델과 도구 이름 (2026-04 기준):

| 에이전트 | 파일 | 입력 도구 | 출력 도구 | 기본 모델 |
|---|---|---|---|---|
| PersonaAgent | `persona_agent.py` | `load_customer_feedback` | `save_persona` | `claude-sonnet-4-6` |
| NBAAgent | `nba_agent.py` | `load_persona_and_recent_notes` | `save_nba_recommendations` | `claude-opus-4-6` |
| ActivityAgent | `activity_agent.py` | `load_nba_and_context` | `save_activity_schedule` | `claude-opus-4-6` |
| QCAgent | `qc_agent.py` | `load_all_agent_outputs` | `save_qc_report` | `claude-opus-4-6` |
| OrchestratorAgent | `orchestrator.py` | `run_*_agent`, `get_customer_info` | (output/…md 저장) | `claude-opus-4-6` |
| DislikeCheckerAgent | `dislike_checker_agent.py` | — | `save_red_flag_results` | `claude-sonnet-4-6` |
| ChatAgent | `chat_agent.py` | `list/search/get_customers`, `get_persona/nba/activities/qc_report`, `list/get/search_sales_notes` (모두 read-only) | — | `claude-sonnet-4-6` |

모델은 런타임에 `_model_setting["model"]`로 오버라이드 가능 (`POST /api/model`).

## 웹 API 엔드포인트 (`web/app.py`)

전체 경로는 README 참조. 그룹별 대표:

### 개별 에이전트 SSE
- `GET /api/analyze/{id}` — 전체 파이프라인 (Orchestrator)
- `GET /api/run/{persona|nba|activity|qc}/{id}` — 단독 실행 (persona·nba는 `?force=true`로 증분 해제)

### 전체 고객 일괄 SSE (의존성 자동 스킵)
- `GET /api/run/persona-all?force=...` — 전체 페르소나 일괄
- `GET /api/run/nba-all?force=...` — Persona 없는 고객 스킵
- `GET /api/run/activity-all` — NBA 없는 고객 스킵
- `GET /api/run/qc-all` — Persona/NBA/Activity 중 하나라도 없으면 스킵 (누락 항목 명시)

### 전체 조회
- `GET /api/all-{personas|nba|activities|qc|sales-notes}` — 고객 메타 병합 + 정렬
- `/api/all-nba`는 매칭 노트의 red-flag 메타를 NBA 레코드에 조인 (N+1 호출 방지)

### CRUD / Chat / 시스템
- `GET|POST|DELETE /api/customers` — 자동 채번(`next_customer_id`), 삭제 시 연관 결과 캐스케이드
- `GET|POST|DELETE /api/sales-notes` + `/api/sales-notes/upload` + `/api/sales-notes/bulk-commit` + `/api/sales-notes/check-dislikes`
- `POST /api/chat` — ChatAgent (무상태, 클라가 대화 이력 유지)
- `GET|POST /api/models` / `/api/model`
- `GET /api/debug`, `GET /api/debug/env` — Railway 진단

## SSE 이벤트 형식

**개별 실행**:
```json
{"type": "log",   "text": "에이전트 실행 로그..."}
{"type": "done",  "completed_at": "2026-04-24 14:32:05"}
{"type": "error", "text": "오류 메시지..."}
```

**일괄 실행** (추가):
```json
{"type": "progress", "index": 3, "total": 11, "customer_id": "C003",
 "company_name": "한국투자증권", "status": "started|done|skipped|error", "error": "..."}
{"type": "done", "total": 11, "succeeded": 8, "failed": 1, "skipped": 2,
 "completed_at": "2026-04-24 14:32:05"}
```

일괄 실행 중복 방지는 `running_set`에 `"persona-all"`/`"nba-all"`/`"activity-all"`/`"qc-all"` 키 잠금(**주의사항** 참조).

## 프론트엔드 컨벤션

`web/templates/index.html` 단일 파일에 7개 탭이 묶여 있음:

1. 고객 대시보드 (카드/리스트 + AI Chat 사이드바 + 4종 일괄 실행 버튼)
2. 고객 전체 조회
3. 세일즈 노트 전체 조회
4. 세일즈 노트 일괄 업로드
5. 페르소나 전체 조회
6. 전체 NBA 추천
7. 전체 QC 검수

**탭 로딩 규칙**: `tabLoaded = { tabKey: bool, ... }` 객체로 lazy load. 탭 전환 시 `false`면 로더 실행 후 `true`. 일괄 실행 완료 후 대응 탭을 `false`로 되돌려 다음 진입 시 재조회.

**SSE 진행 패널 패턴**: 대시보드의 4종 버튼 각각 `startBulk{Persona|Nba|Activity|Qc}Update()`가 `bulk{X}Panel` / `bulk{X}ProgressBar` / `bulk{X}ProgressList` DOM을 조작. 4개 함수가 구조 동일 — 추가 시 한 개 복제.

**색상 컨벤션**: 대시보드 버튼은 파이프라인 단계를 색으로 구분 — Persona `primary`, NBA `warning`, Activity `success`, QC `info`.

**Activity 리스트**: 컬럼 헤더 클릭으로 정렬. `_activitySort = {key, dir}` 상태 + `setActivitySort(key)` 토글. 한국어 정렬은 `localeCompare(.., 'ko')`.

## 주의사항 (Gotchas)

편집 시 반복되는 함정들:

1. **`escHtml` 파일마다 구현이 다름**:
   - `index.html:3497` — `&<>`만 이스케이프 (단일/이중 따옴표 미이스케이프)
   - `customer.html:408` — `&<>"`까지 이스케이프, `String(s ?? '')` 처리
   - **단일 따옴표가 어떤 구현에서도 이스케이프되지 않음** → `onclick="foo('${escHtml(x)}')"` 패턴에 LLM/DB 값 삽입 시 JS 탈출 가능. 새 렌더 코드 추가 시 인라인 onclick 대신 `data-*` + 이벤트 위임 권장.

2. **전역 가변 상태**:
   - `_model_setting: dict` — 요청 간 공유. 멀티유저 환경에서 누가 `POST /api/model`을 호출하면 모두에게 반영됨.
   - `running_set: set` — check-then-act 레이스 존재. 동시 기동 방지가 강하게 필요하면 `threading.Lock` 추가 필요.

3. **`seed_customers_if_empty` 이름 ≠ 동작**: 이름은 "비어있을 때만"이지만 실제는 **항상 JSON → DB upsert**(`data_tools.py:50-118`). 로컬 SQLite 재기동 시 웹에서 수정한 고객 데이터가 JSON으로 덮일 수 있음. Railway 경로는 `lifespan`에서 psycopg2 직접 upsert로 우회.

4. **`load_dotenv` 동작 차이**: 웹은 `override=False` (env 우선), CLI는 `override=True` (.env 우선). 같은 머신에서 두 경로 디버깅 시 환경변수 값 차이 주의.

5. **일괄 실행 의존성 체인**: Persona → NBA → Activity → QC. 상위 에이전트 결과가 없으면 하위 에이전트는 스킵 이벤트 발생. 새 일괄 엔드포인트 추가 시 `dt.get_persona(cid)` / `dt.get_nba(cid)` / `dt.get_activities(cid)` 체크 패턴 복제.

6. **OpenRouter free tier는 rate limit 빈번**: 로컬 테스트 시 Gemma/GPT-OSS/GLM/MiniMax 선택 시 429 재시도가 최대 4회 × 지수 백오프 → 응답 최대 ~75초 지연 가능.

## 최종 보고서 출력

`output/orchestrator_{customer_id}_{timestamp}.md`로 저장됩니다. `output/` 디렉토리는 `.gitignore`에 포함.
