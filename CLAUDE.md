# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# 단일 고객 분석
python src/main.py C001

# 커스텀 태스크 지정
python src/main.py C001 --task "반도체 섹터 집중 분석만 수행해주세요"

# 전체 고객 순차 분석
python src/main.py --all

# 의존성 설치
pip install -r requirements.txt
```

## Environment

`.env` 파일을 프로젝트 루트에 생성 후 실행:

```
ANTHROPIC_API_KEY=sk-ant-...
```

`load_dotenv(override=True)`로 로드되므로 환경변수보다 `.env`가 우선됩니다.

## Architecture

### 멀티에이전트 파이프라인

```
main.py → OrchestratorAgent → PersonaAgent → NBAAgent → ActivityAgent → QCAgent
```

Orchestrator는 각 하위 에이전트를 **Claude tool_use** 패턴으로 등록하여 LLM이 실행 순서를 자율 결정합니다. 표준 순서는 Persona → NBA → Activity → QC이며, QC가 fail을 반환하면 문제 에이전트를 최대 1회 재실행합니다.

### BaseAgent (`src/agents/base_agent.py`)

모든 에이전트의 공통 Agentic Loop 구현. 핵심 동작:
- `max_tokens=16000`으로 설정, `stop_reason == "max_tokens"` 시 최대 5회까지 자동으로 계속 생성 요청
- `stop_reason == "end_turn"` 시 루프 종료
- 하위 클래스는 `execute_tool(tool_name, tool_input)` 만 구현하면 됨

### 데이터 레이어 (`src/tools/data_tools.py`)

모든 JSON 파일 읽기/쓰기를 담당하는 순수 함수 모음. 에이전트는 직접 파일 접근 없이 이 모듈만 사용합니다.

- **원본 데이터** (읽기 전용): `data/customers.json`, `data/sales_notes.json`, `data/action_plans.json`
- **에이전트 출력** (읽기/쓰기): `data/personas.json`, `data/nba_results.json`, `data/activities.json`, `data/qc_reports.json`
- `build_raw_context(customer_id)`: 원본 데이터 전체 조합 (Persona, NBA Agent 입력용)
- `build_full_context(customer_id)`: 에이전트 결과물까지 포함 (QC Agent 입력용)

### 에이전트별 역할

| 에이전트 | 입력 도구 | 출력 도구 | 모델 |
|---|---|---|---|
| PersonaAgent | `load_customer_raw_data` | `save_persona` | claude-opus-4-6 |
| NBAAgent | `load_persona_and_history` | `save_nba_recommendations` | claude-opus-4-6 |
| ActivityAgent | `load_nba_and_context` | `save_activity_schedule` | claude-opus-4-6 |
| QCAgent | `load_all_agent_outputs` | `save_qc_report` | claude-opus-4-6 |
| OrchestratorAgent | `run_*_agent`, `get_customer_info` | (최종 보고서 파일 저장) | claude-opus-4-6 |

### 최종 보고서 출력

`output/orchestrator_{customer_id}_{timestamp}.md` 로 저장됩니다. `output/` 디렉토리는 `.gitignore`에 포함되어 있습니다.
