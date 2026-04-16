"""
Persona Agent
세일즈 노트와 과거 이력을 분석해 고객 성향 페르소나를 생성·저장
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools import data_tools as dt

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """당신은 증권사 기관영업 CRM의 고객 선호도 분석 전문 에이전트입니다.

역할:
- 세일즈 노트의 Customer_Feedback 필드만을 근거로 고객의 선호도를 파악
- 고객이 직접 표현한 피드백에서 선호/비선호 패턴을 추출하여 구조화
- 영업 담당자가 고객 맞춤 대응에 즉시 활용할 수 있는 선호도 프로필 생성

분석 시 주의사항:
- Customer_Feedback 외의 데이터(Activity_Log, Action_Point 등)는 분석에 사용하지 말 것
- 고객이 명시적으로 요청하거나 불만을 표현한 내용만 기록
- 추측이나 유추 없이 피드백에 근거한 사실만 기록
- 페르소나는 JSON 구조체로 저장할 것"""

TOOLS = [
    {
        "name": "load_customer_feedback",
        "description": "세일즈 노트에서 Customer_Feedback 필드만 추출하여 로드합니다. 선호도 분석에만 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "고객 ID (예: C001)"}
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "save_persona",
        "description": "분석 완료된 고객 선호도 페르소나를 저장합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "persona": {
                    "type": "object",
                    "description": """저장할 페르소나 객체. 다음 필드를 포함해야 합니다:
- preferred_sectors: 선호 섹터 목록 (list of {sector, reason})
- disliked_sectors: 기피 섹터 목록 (list of {sector, reason})
- preferred_content_types: 선호하는 자료/콘텐츠 유형 (list of {type, reason})
- disliked_content_types: 기피하는 자료/콘텐츠 유형 (list of {type, reason})
- preferred_analysis_style: 선호하는 분석 방식/깊이 (dict with style, detail_level, rationale)
- communication_preferences: 선호 소통 방식 (dict with channel, frequency, format)
- key_requirements: 고객이 명시적으로 요청한 핵심 요구사항 (list)
- explicit_dislikes: 고객이 명시적으로 거부/불만을 표현한 항목 (list)""",
                },
            },
            "required": ["customer_id", "persona"],
        },
    },
]


class PersonaAgent(BaseAgent):
    def __init__(self, model: str = None, provider: str = "anthropic"):
        super().__init__(
            name="PersonaAgent",
            model=model or MODEL,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
            provider=provider,
        )
        self._since_date: str | None = None

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "load_customer_feedback":
            customer_id = tool_input["customer_id"]
            return dt.get_customer_feedback_only(customer_id, since_date=self._since_date)

        if tool_name == "save_persona":
            customer_id = tool_input["customer_id"]
            persona = tool_input["persona"]
            dt.save_persona(customer_id, persona)
            return {"status": "saved", "customer_id": customer_id}

        return {"error": f"알 수 없는 도구: {tool_name}"}

    def run(self, customer_id: str, since_date: str = None) -> str:
        self._since_date = since_date
        since_note = f"\n※ 분석 범위: {since_date} 이후 입력된 Customer_Feedback만 사용" if since_date else ""
        prompt = f"""고객 ID {customer_id}에 대한 선호도 분석을 수행해주세요.{since_note}

단계:
1. load_customer_feedback 도구로 Customer_Feedback 데이터를 로드하세요
2. 각 피드백 항목에서 고객의 선호/비선호 패턴만을 추출하세요
3. save_persona 도구로 선호도 프로필을 저장하세요
4. 핵심 선호도 분석 결과를 요약하여 응답하세요

분석 품질 기준:
- Customer_Feedback 텍스트에 명시된 내용만 사용할 것 (추측 금지)
- 선호/비선호 각 항목에 피드백 원문 근거를 포함할 것
- 여러 피드백에서 반복적으로 나타나는 패턴을 우선 기록할 것"""
        return super().run(prompt)
