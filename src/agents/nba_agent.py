"""
NBA Agent (Next Best Action)
페르소나 + 최근 3개월 세일즈 노트(recency 가중치) 기반 최적 영업 행동 추천.
- 가장 최근 노트의 Action_Point를 최우선 참고
- 기한은 구체적인 날짜로 표시
- 관련 노트 ID / Action_Point 비교 포함
- CRM 담당자 → 세일즈 담당자 승인 워크플로우 포함
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools import data_tools as dt

MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """당신은 증권사 기관영업 전문 Next Best Action 추천 에이전트입니다.

역할:
- 고객 페르소나와 최근 세일즈 노트를 종합하여 최적의 영업 행동을 우선순위별로 추천
- 가장 최근 세일즈 노트의 Action_Point를 가장 중요한 참고 기준으로 삼을 것
- 분석일 기준 최대 3개월 이내 노트만 참고하며, 최근 노트일수록 높은 가중치 적용
- 모든 기한은 "이번 주", "2주 내" 같은 표현 없이 반드시 구체적인 날짜(YYYY-MM-DD)로 표시

추천 원칙:
1. 가장 최근 노트의 Action_Point → 즉시 실행 최우선 액션으로 반영
2. recency_weight가 높은 노트의 내용일수록 더 강하게 반영
3. 고객 페르소나의 선호도(preferred_sectors, key_requirements 등)와 연계
4. 고객이 싫어하는 접근 방식(explicit_dislikes)은 철저히 회피
5. 각 액션은 SMART 기준(Specific·Measurable·Achievable·Relevant·Time-bound)으로 작성
6. 최우선 순위 액션은 반드시 관련 노트 ID 및 해당 Action_Point와 비교하여 근거 제시"""

TOOLS = [
    {
        "name": "load_persona_and_recent_notes",
        "description": "저장된 고객 페르소나와 분석일 기준 최근 3개월 세일즈 노트(recency_weight 포함)를 통합 로드합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "analysis_date": {
                    "type": "string",
                    "description": "분석 기준일 (YYYY-MM-DD). 생략 시 오늘 날짜 사용.",
                },
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "save_nba_recommendations",
        "description": "생성된 NBA 추천 결과를 저장합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "nba_data": {
                    "type": "object",
                    "description": """NBA 데이터 구조:
- summary: 전체 상황 요약 (string)
- analysis_date: 분석일 (YYYY-MM-DD)
- risk_level: 고객 이탈 위험도 (high/medium/low)
- reference_notes: 참고한 세일즈 노트 목록 (list of {note_id, activity_date, action_point, recency_weight})
- top_priority_comparison: 최우선 액션과 노트 Action_Point 비교
  {note_id, activity_date, action_point_from_note, nba_top_priority_action, rationale}
- actions: 우선순위별 영업 액션 list (rank 1이 최우선)
  각 action: {
    rank,
    title,
    rationale,
    how_to,
    deadline (YYYY-MM-DD 구체적 날짜),
    related_note_ids (list),
    expected_reaction,
    success_metric,
    approval: {
      status ("ai_proposed" 고정으로 초기화),
      ai_proposed_at (분석일),
      crm_approved_at (null),
      crm_approved_by (null),
      sales_approved_at (null),
      sales_approved_by (null)
    }
  }
- avoid_actions: 절대 금지 행동 list
- expected_outcomes: 예상 성과 (3개월 기준, string)""",
                },
            },
            "required": ["customer_id", "nba_data"],
        },
    },
]


class NBAAgent(BaseAgent):
    def __init__(self, model: str = None, provider: str = "anthropic"):
        super().__init__(
            name="NBAAgent",
            model=model or MODEL,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
            provider=provider,
        )
        self._since_date: str | None = None

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "load_persona_and_recent_notes":
            cid = tool_input["customer_id"]
            analysis_date = tool_input.get("analysis_date")
            recent = dt.get_recent_notes_with_weights(cid, analysis_date=analysis_date, since_date=self._since_date)
            persona = dt.get_persona(cid)
            return {
                "customer_id": cid,
                "analysis_date": recent["analysis_date"],
                "persona": persona,
                "recent_notes": recent,
            }

        if tool_name == "save_nba_recommendations":
            dt.save_nba(tool_input["customer_id"], tool_input["nba_data"])
            return {"status": "saved", "customer_id": tool_input["customer_id"]}

        return {"error": f"알 수 없는 도구: {tool_name}"}

    def run(self, customer_id: str, since_date: str = None) -> str:
        self._since_date = since_date
        analysis_date = datetime.today().strftime("%Y-%m-%d")
        since_note = f"\n※ 분석 범위: {since_date} 이후 입력된 세일즈 노트만 참고" if since_date else ""
        prompt = f"""고객 ID {customer_id}의 Next Best Action을 분석해주세요.
분석일: {analysis_date}{since_note}

단계:
1. load_persona_and_recent_notes 도구로 페르소나와 최근 3개월 노트를 로드하세요
   (analysis_date: "{analysis_date}" 전달)
2. most_recent_note의 Action_Point를 최우선 참고하여 즉시 실행 액션을 설계하세요
3. recency_weight가 높은 노트일수록 더 강하게 반영하세요
4. 모든 deadline은 분석일({analysis_date}) 기준 구체적인 날짜(YYYY-MM-DD)로 작성하세요
5. top_priority_comparison에 최우선 액션과 관련 노트의 Action_Point를 대조하여 근거를 명확히 하세요
6. 모든 action의 approval.status는 "ai_proposed"로 초기화하고, 나머지 승인 필드는 null로 설정하세요
7. save_nba_recommendations 도구로 결과를 저장하세요
8. 최우선 액션과 그 근거를 요약하여 응답하세요

핵심 판단 기준:
- 가장 최근 노트 Action_Point > 페르소나 선호도 > 오래된 노트 순으로 우선순위 부여
- 고객 페르소나의 explicit_dislikes는 어떤 이유로도 건드리지 않음
- 기한 표현은 반드시 날짜(예: {analysis_date[:4]}-05-01)로만 작성"""
        return super().run(prompt)
