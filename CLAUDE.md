# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 웹 서버 실행 (개발)
uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload

# 웹 서버 실행 (프로덕션)
uvicorn web.app:app --host 0.0.0.0 --port 8000

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

`load_dotenv(override=False)`로 로드되므로 Railway 등 환경변수가 `.env`보다 우선됩니다.

## Architecture

### 멀티에이전트 파이프라인

```
main.py / web/app.py → OrchestratorAgent → PersonaAgent → NBAAgent → ActivityAgent → QCAgent
```

Orchestrator는 각 하위 에이전트를 **Claude tool_use** 패턴으로 등록하여 LLM이 실행 순서를 자율 결정합니다. 표준 순서는 Persona → NBA → Activity → QC이며, QC가 fail을 반환하면 문제 에이전트를 최대 1회 재실행합니다.

### BaseAgent (`src/agents/base_agent.py`)

모든 에이전트의 공통 Agentic Loop 구현. 핵심 동작:
- `max_tokens=16000`으로 설정, `stop_reason == "max_tokens"` 시 최대 5회까지 자동으로 계속 생성 요청
- `stop_reason == "end_turn"` 시 루프 종료
- 하위 클래스는 `execute_tool(tool_name, tool_input)` 만 구현하면 됨

### 데이터 레이어 (`src/tools/data_tools.py`)

모든 데이터 읽기/쓰기를 담당하는 순수 함수 모음. 에이전트는 직접 파일·DB 접근 없이 이 모듈만 사용합니다.

- **정적 원본** (읽기 전용 JSON): `data/customers.json`, `data/action_plans.json`
- **영업 노트** (DB, 웹에서 조회·추가 가능): `sales_notes` 테이블
  - 최초 실행 시 `data/sales_notes.json` → DB 자동 이전 (`seed_sales_notes_if_empty`)
  - `get_sales_notes(customer_id)`: DB 조회, 실패 시 JSON fallback
  - `add_sales_note(customer_id, note_data)`: 새 노트 저장, `note_id` 자동 생성
- **에이전트 출력** (DB): `personas`, `nba_results`, `activities`, `qc_reports` 테이블
- `build_raw_context(customer_id)`: 원본 데이터 + 영업 노트 조합 (Persona, NBA Agent 입력용)
- `build_full_context(customer_id)`: 에이전트 결과물까지 포함 (QC Agent 입력용)

### DB 모델 (`src/db/database.py`)

SQLite(로컬) / PostgreSQL(Railway) 자동 전환. 테이블:

| 테이블 | 모델 클래스 | PK | 설명 |
|---|---|---|---|
| `personas` | `Persona` | `customer_id` | 고객 페르소나 |
| `nba_results` | `NBAResult` | `customer_id` | NBA 추천 결과 |
| `activities` | `ActivitySchedule` | `customer_id` | 활동 일정 |
| `qc_reports` | `QCReport` | `customer_id` | QC 검수 보고서 |
| `sales_notes` | `SalesNote` | `note_id` | 영업 노트 (웹 CRUD) |

### 에이전트별 역할

| 에이전트 | 입력 도구 | 출력 도구 | 모델 |
|---|---|---|---|
| PersonaAgent | `load_customer_raw_data` | `save_persona` | claude-opus-4-6 |
| NBAAgent | `load_persona_and_history` | `save_nba_recommendations` | claude-opus-4-6 |
| ActivityAgent | `load_nba_and_context` | `save_activity_schedule` | claude-opus-4-6 |
| QCAgent | `load_all_agent_outputs` | `save_qc_report` | claude-opus-4-6 |
| OrchestratorAgent | `run_*_agent`, `get_customer_info` | (최종 보고서 파일 저장) | claude-opus-4-6 |

### 웹 API 엔드포인트 (`web/app.py`)

| Method | Path | 설명 |
|---|---|---|
| GET | `/` | 고객 대시보드 |
| GET | `/customer/{id}` | 고객 상세 페이지 |
| GET | `/api/customers` | 전체 고객 목록 |
| GET | `/api/customer/{id}` | 고객 분석 결과 조회 |
| GET | `/api/analyze/{id}` | SSE 스트리밍 파이프라인 실행 |
| GET | `/api/sales-notes/{id}` | 고객별 영업 노트 목록 |
| POST | `/api/sales-notes` | 새 영업 노트 추가 |
| GET | `/api/models` | 사용 가능 모델 목록 |
| POST | `/api/model` | 분석 모델 변경 |

### 최종 보고서 출력

`output/orchestrator_{customer_id}_{timestamp}.md` 로 저장됩니다. `output/` 디렉토리는 `.gitignore`에 포함되어 있습니다.
