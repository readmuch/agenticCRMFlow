"""
ChatAgent
대시보드 우하단 챗 패널 전용 에이전트. 읽기 전용 도구로 CRM DB를 조회해
사용자의 질의에 답변한다.

- BaseAgent.run(messages, max_tool_iterations)를 사용해 멀티턴 대화 처리
- 도구는 모두 read-only: 고객/페르소나/NBA/Activity/QC/세일즈 노트 조회 · 검색
- 도구 반복 상한 10회 (무한 루프 방지)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools import data_tools as dt

MODEL = "claude-sonnet-4-6"
MAX_TOOL_ITERATIONS = 10

SYSTEM_PROMPT = """당신은 한국 증권사 기관영업 CRM 시스템에 통합된 AI 어시스턴트입니다.

CRM에는 다음 데이터가 있고 각각을 조회하는 읽기 전용 도구가 제공됩니다:
- 고객 정보 (customer): 회사명, 등급(S/A/B), AUM, 유형, 담당자, 투자 만데이트
- 페르소나 (persona): 선호/기피 섹터·콘텐츠, 분석 스타일, 커뮤니케이션 선호, 명시적 불만/거부
- NBA 추천 (nba): 우선순위별 영업 액션과 승인 상태
- Activity 일정 (activities): NBA 기반 실행 일정
- QC 보고서 (qc_report): 분석 품질 검수 결과
- 세일즈 노트 (sales_notes): 각 미팅/통화의 Activity_Log, Customer_Feedback, Action_Point

행동 원칙:
- 질문에 답하려면 반드시 적절한 도구를 호출해 실제 데이터를 확인한 뒤 답변하세요.
- 도구를 호출하지 않고 추측·기억·일반 상식으로 답하지 마세요. 조회가 불가능한 질문이면 "해당 정보는 시스템에 없거나 아직 분석되지 않았습니다"라고 명확히 밝히세요.
- 고객을 지목할 때 사용자가 회사명만 말하면 `search_customers` 또는 `list_customers`로 customer_id를 먼저 확인하세요.
- 복수 고객/항목을 비교하라는 요청은 각 고객에 대해 도구를 여러 번 호출한 뒤 비교 답변을 작성하세요.
- 답변은 한국어로 간결하게. 근거가 되는 고객 ID, 날짜, 노트 ID 등을 함께 명시하세요.
- 수정·삭제·생성 도구는 제공되지 않습니다 (읽기 전용). 그런 요청이 오면 "시스템에서 해당 작업은 챗이 아닌 전용 UI로 수행하셔야 합니다"라고 답하세요.
- 페르소나 원문을 그대로 인용해야 답변이 명확해지는 경우(예: "명시적 불만 항목이 뭐야?")에는 인용해도 됩니다."""


TOOLS = [
    {
        "name": "list_customers",
        "description": "전체 고객 목록을 요약 필드(customer_id, 회사명, 등급, 유형, AUM, 담당 영업, 투자 만데이트)로 반환합니다.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_customers",
        "description": "회사명/유형/담당 영업/투자 만데이트에 부분 일치하는 고객을 검색합니다 (대소문자 무시).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색어"}
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_customer",
        "description": "customer_id로 특정 고객의 전체 기본 정보(연락처, 만데이트, AUM 등)를 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string", "description": "예: C001"}
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_persona",
        "description": "특정 고객의 페르소나 전체(선호/기피 섹터·콘텐츠, 분석 스타일, 커뮤니케이션 선호, 핵심 요구사항, 명시적 불만/거부 항목, updated_at 등)를 반환합니다. 아직 분석되지 않았으면 null이 반환됩니다.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_nba",
        "description": "특정 고객의 최근 NBA 추천(우선순위 액션, 참고 노트, 최우선 액션 vs 노트 비교, 승인 상태, generated_at 등)을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_activities",
        "description": "특정 고객의 Activity 일정(각 항목의 title, due_date, NBA 승인 상태, 진행 상태 등)과 updated_at을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_qc_report",
        "description": "특정 고객의 QC 검수 보고서(overall_score, verdict, critical_issues, reviewed_at 등)를 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "string"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "list_sales_notes",
        "description": "특정 고객의 세일즈 노트 최신 N건을 요약(note_id, 날짜, 활동유형, 섹터, Action_Point 프리뷰)으로 반환합니다. 전체 본문이 필요하면 get_sales_note를 사용하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "limit": {"type": "integer", "default": 5, "description": "반환 건수 (기본 5)"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_sales_note",
        "description": "note_id로 세일즈 노트 한 건의 전체 본문(Activity_Log, Customer_Feedback, Action_Point 등 모든 필드)을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {"note_id": {"type": "string"}},
            "required": ["note_id"],
        },
    },
    {
        "name": "search_sales_notes",
        "description": "Activity_Log · Customer_Feedback · Action_Point · Sector 필드에 부분 일치하는 세일즈 노트를 전체 고객에서 검색합니다. 최신순 상위 N건 반환.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
]


def _customer_summary(c: dict) -> dict:
    if not c:
        return {}
    return {
        "customer_id": c.get("customer_id"),
        "company_name": c.get("company_name"),
        "tier": c.get("tier"),
        "company_type": c.get("company_type"),
        "aum_billion_krw": c.get("aum_billion_krw"),
        "assigned_salesperson": c.get("assigned_salesperson"),
        "investment_mandate": c.get("investment_mandate", []),
    }


def _note_summary(n: dict) -> dict:
    ap = n.get("Action_Point") or ""
    return {
        "note_id": n.get("note_id"),
        "customer_id": n.get("customer_id") or n.get("_customer_id"),
        "company_name": n.get("_customer_name"),
        "Activity_Date": n.get("Activity_Date") or n.get("date"),
        "Activity_Type": n.get("Activity_Type"),
        "Sector": n.get("Sector"),
        "Sales_Name": n.get("Sales_Name"),
        "Action_Point_preview": (ap[:120] + ("…" if len(ap) > 120 else "")) if ap else "",
    }


class ChatAgent(BaseAgent):
    def __init__(self, model: str = None, provider: str = "anthropic"):
        super().__init__(
            name="ChatAgent",
            model=model or MODEL,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
            provider=provider,
        )

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        try:
            if tool_name == "list_customers":
                customers = dt.get_all_customers() or []
                return {"count": len(customers), "customers": [_customer_summary(c) for c in customers]}

            if tool_name == "search_customers":
                q = str(tool_input.get("query", "")).strip().lower()
                if not q:
                    return {"error": "query가 비어있습니다."}
                customers = dt.get_all_customers() or []
                hits = []
                for c in customers:
                    hay = " ".join([
                        str(c.get("company_name", "")),
                        str(c.get("company_type", "")),
                        str(c.get("assigned_salesperson", "")),
                        " ".join(c.get("investment_mandate", []) or []),
                    ]).lower()
                    if q in hay:
                        hits.append(_customer_summary(c))
                return {"query": q, "count": len(hits), "customers": hits}

            if tool_name == "get_customer":
                cid = tool_input["customer_id"]
                c = dt.get_customer(cid)
                return c or {"customer_id": cid, "error": "고객을 찾을 수 없습니다."}

            if tool_name == "get_persona":
                cid = tool_input["customer_id"]
                p = dt.get_persona(cid)
                if not p:
                    return {"customer_id": cid, "persona": None, "note": "아직 페르소나가 생성되지 않았습니다."}
                return p

            if tool_name == "get_nba":
                cid = tool_input["customer_id"]
                nba = dt.get_nba(cid)
                if not nba:
                    return {"customer_id": cid, "nba": None, "note": "아직 NBA 추천이 생성되지 않았습니다."}
                return nba

            if tool_name == "get_activities":
                cid = tool_input["customer_id"]
                activities = dt.get_activities(cid) or []
                updated_at = dt.get_activities_updated_at(cid)
                return {
                    "customer_id": cid,
                    "count": len(activities),
                    "updated_at": updated_at,
                    "activities": activities,
                }

            if tool_name == "get_qc_report":
                cid = tool_input["customer_id"]
                qc = dt.get_qc_report(cid)
                if not qc:
                    return {"customer_id": cid, "qc": None, "note": "아직 QC 검수가 실행되지 않았습니다."}
                return qc

            if tool_name == "list_sales_notes":
                cid = tool_input["customer_id"]
                limit = int(tool_input.get("limit") or 5)
                notes = dt.get_sales_notes(cid) or []
                notes = notes[:max(1, limit)]
                return {
                    "customer_id": cid,
                    "count": len(notes),
                    "notes": [_note_summary(n) for n in notes],
                }

            if tool_name == "get_sales_note":
                nid = tool_input["note_id"]
                # 전체 고객 노트를 훑어 단일 매칭 — 소규모 DB라 충분
                customers = dt.get_all_customers() or []
                for c in customers:
                    for n in dt.get_sales_notes(c.get("customer_id", "")) or []:
                        if n.get("note_id") == nid:
                            return n
                return {"note_id": nid, "error": "노트를 찾을 수 없습니다."}

            if tool_name == "search_sales_notes":
                q = str(tool_input.get("query", "")).strip().lower()
                limit = int(tool_input.get("limit") or 10)
                if not q:
                    return {"error": "query가 비어있습니다."}
                customers = dt.get_all_customers() or []
                cid_to_name = {c.get("customer_id"): c.get("company_name") for c in customers}
                all_hits = []
                for cid, name in cid_to_name.items():
                    if not cid:
                        continue
                    for n in dt.get_sales_notes(cid) or []:
                        hay = " ".join([
                            str(n.get("Activity_Log", "")),
                            str(n.get("Customer_Feedback", "")),
                            str(n.get("Action_Point", "")),
                            str(n.get("Sector", "")),
                        ]).lower()
                        if q in hay:
                            m = dict(n)
                            m["_customer_id"] = cid
                            m["_customer_name"] = name
                            all_hits.append(m)
                all_hits.sort(key=lambda x: x.get("Activity_Date") or x.get("date", ""), reverse=True)
                top = all_hits[: max(1, limit)]
                return {
                    "query": q,
                    "total_matches": len(all_hits),
                    "returned": len(top),
                    "notes": [_note_summary(n) for n in top],
                }

            return {"error": f"알 수 없는 도구: {tool_name}"}
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return {"error": f"{type(exc).__name__}: {exc}"}

    def chat(self, messages: list[dict]) -> str:
        """클라이언트가 보내준 멀티턴 대화 이력을 받아 최종 답변 텍스트를 반환."""
        # messages 정규화: [{role, content}] shape 보장
        safe = []
        for m in messages:
            role = m.get("role") if isinstance(m, dict) else getattr(m, "role", None)
            content = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
            if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                safe.append({"role": role, "content": content})
        if not safe:
            return "질문을 입력해 주세요."
        return super().run(safe, max_tool_iterations=MAX_TOOL_ITERATIONS)
