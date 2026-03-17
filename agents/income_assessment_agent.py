"""
agents/income_assessment_agent.py
===================================
Agent: IncomeAssessmentAgent
Weight: 25%
MCP Server: bank-statement-mcp

Responsibilities:
  - Verify stated income against bank statement credits
  - Calculate Debt-to-Income (DTI) / FOIR ratio
  - Check income stability and consistency
  - Verify employer and EPF registration
  - Flag frequent bounces, irregular income

Scoring rules:
  Start at 100, deduct for issues:
    DTI > 60%           → -50 + DTI_CRITICAL (hard stop eligible)
    DTI 45–60%          → -25 + DTI_HIGH
    DTI 35–45%          → -10
    Income mismatch>15% → -20 + INCOME_MISMATCH
    Income mismatch>10% → -10
    Bounce ≥ 3          → -20 + FREQUENT_BOUNCES
    Bounce 1–2          →  -8
    Employer unverified → -10 + EMPLOYER_UNVERIFIED
    EPF not verified    →  -5
    Low min balance     →  -8 + LOW_BALANCE
    Variable income     →  -5
"""

from __future__ import annotations

from agents.base import BaseAgent
from core.models import CustomerApplication, MCPToolCall
from config.settings import settings


class IncomeAssessmentAgent(BaseAgent):
    name   = "IncomeAssessmentAgent"
    weight = 0.25

    def __init__(self):
        self.mcp_url = settings.BANK_MCP_URL

    def _build_tool_call(self, app: CustomerApplication) -> MCPToolCall:
        return MCPToolCall(
            tool       = "full_income_check",
            session_id = app.session_id,
            params     = {
                "pan_number":          app.pan_number,
                "customer_name":       app.customer_name,
                "stated_income":       app.monthly_income,
                "employer_name":       app.employer_name,
                "employment_type":     app.employment_type.value,
                "loan_amount":         app.loan_amount,
                "tenure_months":       app.loan_tenure_months,
                "years_of_employment": app.years_of_employment,
            },
        )

    def _score(self, app: CustomerApplication, data: dict) -> tuple[float, list[str]]:
        score = 100.0
        flags = []

        # DTI check
        dti = data.get("dti_ratio_pct", 40.0)
        if dti > 60:
            score -= 50
            flags.append("DTI_CRITICAL")
        elif dti > 45:
            score -= 25
            flags.append("DTI_HIGH")
        elif dti > 35:
            score -= 10

        # Income mismatch
        variance = data.get("income_variance_pct", 0)
        if variance > 15:
            score -= 20
            flags.append("INCOME_MISMATCH")
        elif variance > 10:
            score -= 10

        # Bounces
        bounces = data.get("total_bounces_6m",
                           sum(m.get("bounces", 0) for m in data.get("statements", [])))
        if bounces >= 3:
            score -= 20
            flags.append("FREQUENT_BOUNCES")
        elif bounces > 0:
            score -= 8

        # Employer / EPF
        if not data.get("employer_verified", True):
            score -= 10
            flags.append("EMPLOYER_UNVERIFIED")
        if not data.get("epf_verified", True):
            score -= 5

        # Balance stability
        verified_income = data.get("verified_monthly_income", app.monthly_income)
        min_bal = data.get("min_balance_6m", verified_income * 0.1)
        if min_bal < verified_income * 0.05:
            score -= 8
            flags.append("LOW_BALANCE")

        # Income stability
        if data.get("income_stability") == "VARIABLE":
            score -= 5

        # Short employment tenure
        if data.get("employment_tenure_months", 24) < 6:
            score -= 10
            flags.append("SHORT_EMPLOYMENT")

        return score, flags
