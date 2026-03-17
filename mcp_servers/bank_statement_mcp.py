"""
mcp_servers/bank_statement_mcp.py
===================================
MCP Server: bank-statement-mcp

Real integrations (MOCK_DATA=false):
  - Account Aggregator (AA) Framework (RBI-regulated)
  - FIP (Financial Information Provider) APIs
  - Perfios / Finbox bank statement analyser

Tools exposed:
  - get_bank_statements   → 6-month transaction history
  - calculate_income      → Net monthly income + salary verification
  - calculate_dti         → Debt-to-income ratio
  - verify_employer       → Employment verification via payroll APIs

Mock behaviour:
  - Verified income ≈ stated income ± 5%
  - DTI calculated from stated loan + existing EMI (15–25% of income)
  - Bounce count: 0–2 (realistic)
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List

from mcp_servers.base import BaseMCPServer
from core.models import MCPToolCall


class BankStatementMCPServer(BaseMCPServer):
    server_name = "bank-statement-mcp"

    async def _mock_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        tool = tool_call.tool
        p    = tool_call.params

        if tool == "get_bank_statements":
            return self._build_statements(p)
        elif tool == "calculate_income":
            return self._build_income(p)
        elif tool == "calculate_dti":
            return self._build_dti(p)
        elif tool == "verify_employer":
            return self._build_employer(p)
        elif tool == "full_income_check":
            inc = self._build_income(p)
            dti = self._build_dti({**p, "verified_income": inc["verified_monthly_income"]})
            emp = self._build_employer(p)
            return {**inc, **dti, **emp}
        else:
            raise ValueError(f"Unknown tool: {tool}")

    # ── Builders ──────────────────────────────────────────────────────────

    def _build_statements(self, p: dict) -> Dict[str, Any]:
        seed   = self._seed(p.get("pan_number", ""), p.get("customer_name", ""))
        rng    = random.Random(seed)
        income = p.get("stated_income", 50_000)

        months = []
        for i in range(6):
            month_date = datetime.now() - timedelta(days=30 * i)
            credit = round(income * rng.uniform(0.95, 1.10), 2)
            debit  = round(credit  * rng.uniform(0.60, 0.85), 2)
            months.append({
                "month":           month_date.strftime("%Y-%m"),
                "opening_balance": round(rng.uniform(5_000, 50_000), 2),
                "total_credit":    credit,
                "total_debit":     debit,
                "closing_balance": round(credit - debit + rng.uniform(3_000, 20_000), 2),
                "salary_credit":   True,
                "salary_amount":   round(income * rng.uniform(0.97, 1.02), 2),
                "bounces":         0 if rng.random() > 0.15 else 1,
            })

        return {
            "statements":             months,
            "bank_name":              rng.choice(["HDFC Bank", "ICICI Bank", "SBI", "Axis Bank", "Kotak Mahindra"]),
            "account_type":           "SAVINGS",
            "account_number_masked":  f"XXXX XXXX {rng.randint(1000, 9999)}",
            "statement_period":       "6 months",
            "total_bounces_6m":       sum(m["bounces"] for m in months),
            "aa_consent_id":          f"AA-{uuid.uuid4().hex[:12].upper()}",
            "fetched_at":             datetime.now().isoformat(),
        }

    def _build_income(self, p: dict) -> Dict[str, Any]:
        seed    = self._seed(p.get("pan_number", ""), p.get("employer_name", ""))
        rng     = random.Random(seed)
        stated  = p.get("stated_income", 50_000)

        # Verified = stated ± 5%
        verified = round(stated * rng.uniform(0.95, 1.05), 2)
        match_pct = abs(verified - stated) / stated

        return {
            "stated_monthly_income":    stated,
            "verified_monthly_income":  verified,
            "income_match":             match_pct < 0.10,
            "income_variance_pct":      round(match_pct * 100, 1),
            "income_source":            p.get("employment_type", "salaried").upper(),
            "income_stability":         "STABLE" if rng.random() > 0.15 else "VARIABLE",
            "salary_credits_verified":  6,
            "avg_monthly_credit":       round(verified * rng.uniform(1.01, 1.08), 2),
            "min_balance_6m":           round(verified * rng.uniform(0.05, 0.20), 2),
            "employer_verified":        True,
            "employment_tenure_months": int(p.get("years_of_employment", 2) * 12),
            "income_verification_ref":  f"INC-{uuid.uuid4().hex[:8].upper()}",
        }

    def _build_dti(self, p: dict) -> Dict[str, Any]:
        seed   = self._seed(p.get("pan_number", ""))
        rng    = random.Random(seed)
        income = p.get("verified_income", p.get("stated_income", 50_000))
        loan   = p.get("loan_amount", 500_000)
        tenure = p.get("tenure_months", 36)

        # EMI using flat rate approximation
        rate_monthly  = 0.11 / 12
        proposed_emi  = round(loan * rate_monthly / (1 - (1 + rate_monthly) ** -tenure), 2)
        existing_emis = round(income * rng.uniform(0.08, 0.22), 2)
        total_oblig   = proposed_emi + existing_emis
        dti           = round((total_oblig / income) * 100, 1)

        return {
            "proposed_emi":              proposed_emi,
            "existing_emi_obligations":  existing_emis,
            "total_monthly_obligations": round(total_oblig, 2),
            "dti_ratio_pct":             dti,
            "dti_status":                "ACCEPTABLE" if dti < 45 else ("HIGH" if dti < 60 else "CRITICAL"),
            "foir":                      round(total_oblig / income, 2),   # Fixed Obligation to Income Ratio
            "disposable_income":         round(income - total_oblig, 2),
        }

    def _build_employer(self, p: dict) -> Dict[str, Any]:
        seed = self._seed(p.get("employer_name", ""), p.get("pan_number", ""))
        rng  = random.Random(seed)

        return {
            "employer_verified":     True,
            "employer_name":         p.get("employer_name", ""),
            "employer_category":     rng.choice(["LARGE_CORP", "MNC", "SME", "PSU", "STARTUP"]),
            "employer_stability":    rng.choice(["HIGH", "HIGH", "MEDIUM"]),
            "epf_verified":          rng.random() > 0.1,
            "epf_member_id":         f"MH/{rng.randint(10,99)}/{rng.randint(10000,99999)}",
            "esic_verified":         rng.random() > 0.3,
        }

    async def _real_response(self, tool_call: MCPToolCall) -> dict:
        """Production: call real RBI Account Aggregator / Perfios APIs."""
        raise NotImplementedError("Implement real Account Aggregator integration here.")

    def tools(self):
        return ["calculate_income", "calculate_dti", "get_bank_summary"]

if __name__ == "__main__":
    import os
    port = int(os.environ.get("BANK_MCP_PORT", 8003))
    print(f"Starting bank-statement-mcp on port {port}  [mock={os.environ.get('MOCK_DATA','true')}]")
    BankStatementMCPServer().serve(port=port)
