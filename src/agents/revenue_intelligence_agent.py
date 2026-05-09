"""
Revenue Intelligence Agent
Proxy signals from sales notes are used to estimate engagement, wallet influence,
service value, and opportunity signals when commission, broker vote, and wallet
share data are not available.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools import data_tools as dt

MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = """You are a sell-side Revenue Intelligence analyst for an institutional CRM.

Use proxy signals only. Do not claim actual commission, wallet share, broker vote,
or realized revenue unless explicit outcome data is provided. In this project,
those outcome datasets are usually unavailable, so the correct output is
Revenue Intelligence proxy analysis.

Your job:
- Read recent sales notes, customer profile, persona, and optional NBA result.
- Tag each interaction by service/product/intent signals.
- Estimate engagement momentum, wallet influence proxy, service ROI proxy, and retention risk.
- Explain evidence with note_id references.
- Produce opportunity signals that can later inform NBA, but do not overwrite NBA.

Proxy signal guidance:
- High-value service types: corporate_access, analyst_call, bespoke_research,
  trading_liquidity, sales_coverage, research_distribution.
- Strong wallet influence signals: explicit follow-up request, decision maker access,
  positive feedback, position/trade/liquidity language, recurring service request,
  condition before increasing exposure, request for model/data/backtest.
- Risk signals: explicit dissatisfaction, weak evidence, stale engagement, red flag
  from dislike checker, repeated unresolved request.

Always save a JSON object with:
- proxy_mode: true
- summary
- analysis_date
- analysis_window: {from, to}
- client_scores: {engagement_momentum, wallet_influence_proxy, service_roi_proxy, retention_risk}
- service_mix: list of {service_type, count, avg_score, evidence_note_ids}
- opportunity_signals: list of {signal, strength, evidence_note_ids, recommended_action, nba_candidate}
- proxy_attribution: list of {note_id, service_type, attribution_weight, reason}
- note_enrichment: list of {note_id, ri_tags, ri_scores}
- limitations: list of strings
Scores are 0-100 integers. attribution_weight values should roughly sum to 1.0 when evidence exists."""

TOOLS = [
    {
        "name": "load_revenue_context",
        "description": "Load customer, persona, NBA, and recent sales notes with recency weights.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "analysis_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "save_revenue_intelligence",
        "description": "Save customer-level RI result and note-level RI enrichment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "string"},
                "revenue_data": {"type": "object"},
            },
            "required": ["customer_id", "revenue_data"],
        },
    },
]


class RevenueIntelligenceAgent(BaseAgent):
    def __init__(self, model: str = None, provider: str = "anthropic"):
        super().__init__(
            name="RevenueIntelligenceAgent",
            model=model or MODEL,
            system_prompt=SYSTEM_PROMPT,
            tools=TOOLS,
            provider=provider,
        )

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "load_revenue_context":
            cid = tool_input["customer_id"]
            analysis_date = tool_input.get("analysis_date")
            recent = dt.get_recent_notes_with_weights(cid, analysis_date=analysis_date, months=3)
            return {
                "customer": dt.get_customer(cid),
                "persona": dt.get_persona(cid),
                "nba": dt.get_nba(cid),
                "recent_notes": recent,
                "red_flag_notes": [
                    {
                        "note_id": n.get("note_id"),
                        "matched": n.get("_red_flag_matched", ""),
                        "reason": n.get("_red_flag_reason", ""),
                    }
                    for n in dt.get_sales_notes(cid)
                    if n.get("_red_flag")
                ],
            }

        if tool_name == "save_revenue_intelligence":
            cid = tool_input["customer_id"]
            revenue_data = self._normalize_revenue_data(tool_input.get("revenue_data") or {})
            for item in revenue_data.get("note_enrichment") or []:
                note_id = item.get("note_id")
                if note_id:
                    dt.update_note_revenue_intelligence(
                        note_id,
                        ri_tags=item.get("ri_tags") or {},
                        ri_scores=item.get("ri_scores") or {},
                    )
            dt.save_revenue_intelligence(cid, revenue_data)
            return {"status": "saved", "customer_id": cid}

        return {"error": f"Unknown tool: {tool_name}"}

    @staticmethod
    def _clamp_score(value, default=0) -> int:
        try:
            return max(0, min(100, int(round(float(value)))))
        except (TypeError, ValueError):
            return default

    def _normalize_revenue_data(self, data: dict) -> dict:
        data.setdefault("proxy_mode", True)
        scores = data.get("client_scores")
        if not isinstance(scores, dict):
            scores = {}
        scores["engagement_momentum"] = self._clamp_score(scores.get("engagement_momentum"), 0)
        scores["wallet_influence_proxy"] = self._clamp_score(scores.get("wallet_influence_proxy"), 0)
        scores["service_roi_proxy"] = self._clamp_score(scores.get("service_roi_proxy"), 0)
        if scores.get("retention_risk") not in ("low", "medium", "high"):
            scores["retention_risk"] = "medium"
        data["client_scores"] = scores

        for item in data.get("note_enrichment") or []:
            ri_scores = item.get("ri_scores")
            if not isinstance(ri_scores, dict):
                ri_scores = {}
            for key in ("engagement_score", "influence_score", "revenue_proxy_score"):
                ri_scores[key] = self._clamp_score(ri_scores.get(key), 0)
            try:
                ri_scores["confidence"] = max(0.0, min(1.0, float(ri_scores.get("confidence", 0))))
            except (TypeError, ValueError):
                ri_scores["confidence"] = 0.0
            item["ri_scores"] = ri_scores

        data.setdefault("limitations", [])
        if not any("proxy" in str(x).lower() for x in data["limitations"]):
            data["limitations"].append("Actual commission, broker vote, and wallet share data are not connected; scores are proxy estimates.")
        return data

    def run(self, customer_id: str) -> str:
        analysis_date = datetime.today().strftime("%Y-%m-%d")
        prompt = f"""Create Revenue Intelligence proxy analysis for customer_id={customer_id}.
analysis_date={analysis_date}

Steps:
1. Call load_revenue_context with customer_id and analysis_date.
2. Analyze only the returned notes and stored customer/persona/NBA context.
3. Use proxy signals, not actual revenue claims.
4. Save the final JSON via save_revenue_intelligence.
5. Reply with a concise summary: top score, top service type, and top opportunity signal."""
        return super().run(prompt, max_tool_iterations=4)
