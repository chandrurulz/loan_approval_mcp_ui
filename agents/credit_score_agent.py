"""
agents/credit_score_agent.py
==============================
Agent: CreditScoreAgent
Weight: 35% (highest weight — credit history is primary predictor)
MCP Server: credit-bureau-mcp

Responsibilities:
  - Fetch CIBIL / Experian score via credit-bureau-mcp
  - Normalise bureau score (300–900) to 0–100 agent score
  - Analyse trade lines for delinquency patterns
  - Flag high utilisation, multiple inquiries, DPD events

Scoring rules:
  Normalised score = (bureau_score - 300) / 6
  Deductions:
    Score < 550           → additional -15 + LOW_CREDIT_SCORE
    Score < 650           → additional  -5
    Delinquent accounts   → -8 each (max 2) + DELINQUENT_ACCOUNTS
    Utilisation > 70%     → -8 + HIGH_UTILIZATION
    DPD 30+               → -10 + DPD_30_PLUS
    Inquiries last 6m > 4 → -8 + MULTIPLE_INQUIRIES
    Write-offs > 0        → -20 + WRITE_OFF_HISTORY
    Settlements > 0       → -10 + SETTLEMENT_HISTORY
    Oldest account < 1yr  → -5 + THIN_CREDIT_FILE
"""

from __future__ import annotations

from agents.base import BaseAgent
from core.models import CustomerApplication, MCPToolCall
from config.settings import settings


class CreditScoreAgent(BaseAgent):
    name   = "CreditScoreAgent"
    weight = 0.35

    def __init__(self):
        self.mcp_url = settings.CREDIT_MCP_URL

    def _build_tool_call(self, app: CustomerApplication) -> MCPToolCall:
        return MCPToolCall(
            tool       = "get_credit_report",
            session_id = app.session_id,
            params     = {
                "pan_number":    app.pan_number,
                "customer_name": app.customer_name,
                "date_of_birth": app.date_of_birth,
            },
        )

    def _score(self, app: CustomerApplication, data: dict) -> tuple[float, list[str]]:
        bureau_score = data.get("credit_score", 600)
        flags = []

        # Normalise 300–900 → 0–100
        score = min(max((bureau_score - 300) / 6.0, 0), 100)

        # Absolute score thresholds
        if bureau_score < 550:
            score -= 15
            flags.append("LOW_CREDIT_SCORE")
        elif bureau_score < 650:
            score -= 5

        # Delinquency
        delinquent = data.get("delinquent_accounts", 0)
        if delinquent > 0:
            score -= min(delinquent * 8, 16)
            flags.append("DELINQUENT_ACCOUNTS")

        # Utilisation
        utilisation = data.get("credit_utilization_pct", 0)
        if utilisation > 70:
            score -= 8
            flags.append("HIGH_UTILIZATION")
        elif utilisation > 50:
            score -= 3

        # DPD (Days Past Due)
        if data.get("dpd_30_plus", 0) > 0:
            score -= 10
            flags.append("DPD_30_PLUS")
        if data.get("dpd_90_plus", 0) > 0:
            score -= 15
            flags.append("DPD_90_PLUS")

        # Inquiries
        inquiries = data.get("inquiries_last_6m", 0)
        if inquiries > 4:
            score -= 8
            flags.append("MULTIPLE_INQUIRIES")
        elif inquiries > 2:
            score -= 3

        # Write-offs and settlements
        if data.get("write_offs", 0) > 0:
            score -= 20
            flags.append("WRITE_OFF_HISTORY")
        if data.get("settlements", 0) > 0:
            score -= 10
            flags.append("SETTLEMENT_HISTORY")

        # Thin credit file
        if data.get("oldest_account_years", 5) < 1:
            score -= 5
            flags.append("THIN_CREDIT_FILE")

        return score, flags
