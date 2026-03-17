"""
mcp_servers/credit_bureau_mcp.py
=================================
MCP Server: credit-bureau-mcp

Real integrations (MOCK_DATA=false):
  - CIBIL (TransUnion) API  → Primary bureau score
  - Experian India API      → Secondary bureau score
  - Equifax India API       → Tertiary bureau score

Tools exposed:
  - get_credit_score   → Fast score-only lookup (50ms SLA)
  - get_credit_report  → Full bureau report with trade lines
  - get_multi_bureau   → Aggregate score from all 3 bureaus

Mock behaviour:
  - Score derived deterministically from PAN via seed
  - Range: 580–800 (realistic distribution)
  - Low-score PANs (seed ending in 0–2) get 500–580 range
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

from mcp_servers.base import BaseMCPServer
from core.models import MCPToolCall


class CreditBureauMCPServer(BaseMCPServer):
    server_name = "credit-bureau-mcp"

    async def _mock_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        tool = tool_call.tool
        p    = tool_call.params

        if tool == "get_credit_score":
            return self._build_score(p)
        elif tool == "get_credit_report":
            return self._build_full_report(p)
        elif tool == "get_multi_bureau":
            return self._build_multi_bureau(p)
        else:
            raise ValueError(f"Unknown tool: {tool}")

    # ── Builders ──────────────────────────────────────────────────────────

    def _build_score(self, p: dict) -> Dict[str, Any]:
        score = self._derive_score(p.get("pan_number", "ABCDE1234F"))
        return {
            "credit_score": score,
            "score_version": "CIBIL v3",
            "bureau": "CIBIL",
            "report_date": datetime.now().strftime("%Y-%m-%d"),
            "score_range": "300-900",
            "report_id": f"CIBIL-S-{uuid.uuid4().hex[:10].upper()}",
        }

    def _build_full_report(self, p: dict) -> Dict[str, Any]:
        pan   = p.get("pan_number", "ABCDE1234F")
        score = self._derive_score(pan)
        seed  = self._seed(pan)
        rng   = random.Random(seed)

        num_accounts  = rng.randint(2, 9)
        active_accs   = rng.randint(1, num_accounts)
        delinquent    = 0 if score > 700 else rng.randint(0, 2)
        utilization   = round(rng.uniform(15, 65), 1)
        dpd_30        = 0 if score > 700 else rng.randint(0, 1)
        inquiries     = rng.randint(0, 4)
        oldest_years  = rng.randint(1, 15)

        trade_lines = []
        account_types = ["Home Loan", "Personal Loan", "Credit Card", "Auto Loan", "Education Loan"]
        for i in range(min(num_accounts, 4)):
            trade_lines.append({
                "account_type":  account_types[i % len(account_types)],
                "lender":        f"Bank {chr(65 + i)}",
                "sanctioned":    round(rng.uniform(50_000, 2_000_000), -3),
                "outstanding":   round(rng.uniform(0, 800_000), -3),
                "dpd":           dpd_30 if i == 0 else 0,
                "status":        "REGULAR" if score > 680 else "SMA-0",
                "opened_date":   (datetime.now() - timedelta(days=rng.randint(180, 2000))).strftime("%Y-%m-%d"),
            })

        return {
            "credit_score":          score,
            "score_version":         "CIBIL v3",
            "bureau":                "CIBIL",
            "report_date":           datetime.now().strftime("%Y-%m-%d"),
            "total_accounts":        num_accounts,
            "active_accounts":       active_accs,
            "closed_accounts":       num_accounts - active_accs,
            "delinquent_accounts":   delinquent,
            "credit_utilization_pct": utilization,
            "oldest_account_years":  oldest_years,
            "inquiries_last_6m":     inquiries,
            "dpd_30_plus":           dpd_30,
            "dpd_60_plus":           0,
            "dpd_90_plus":           0,
            "write_offs":            0,
            "settlements":           0,
            "trade_lines":           trade_lines,
            "payment_history": {
                "on_time_pct": round(95 - (100 - score) / 5, 1),
                "missed_last_12m": dpd_30,
            },
            "report_id": f"CIBIL-F-{uuid.uuid4().hex[:10].upper()}",
        }

    def _build_multi_bureau(self, p: dict) -> Dict[str, Any]:
        pan   = p.get("pan_number", "ABCDE1234F")
        seed  = self._seed(pan)
        base  = self._derive_score(pan)
        rng   = random.Random(seed)

        cibil    = base
        experian = base + rng.randint(-20, 20)
        equifax  = base + rng.randint(-15, 15)
        avg      = round((cibil + experian + equifax) / 3)

        return {
            "aggregate_score": avg,
            "bureaus": {
                "CIBIL":    {"score": cibil,    "available": True},
                "Experian": {"score": experian, "available": True},
                "Equifax":  {"score": equifax,  "available": True},
            },
            "score_variance":   abs(max(cibil, experian, equifax) - min(cibil, experian, equifax)),
            "recommendation":   "USE_AGGREGATE",
            "report_id":        f"MULTI-{uuid.uuid4().hex[:10].upper()}",
        }

    def _derive_score(self, pan: str) -> int:
        """Deterministic bureau score from PAN (580–800 range)."""
        seed = self._seed(pan)
        low_band = (seed % 10) <= 2   # ~30% chance of lower score band
        if low_band:
            return 500 + (seed % 80)
        return 620 + (seed % 180)

    async def _real_response(self, tool_call: MCPToolCall) -> dict:
        """Production: call real CIBIL/Experian/Equifax APIs."""
        raise NotImplementedError("Implement real CIBIL/Experian integration here.")

    def tools(self):
        return ["get_credit_score", "get_credit_report", "get_multi_bureau"]

if __name__ == "__main__":
    import os
    port = int(os.environ.get("CREDIT_MCP_PORT", 8002))
    print(f"Starting credit-bureau-mcp on port {port}  [mock={os.environ.get('MOCK_DATA','true')}]")
    CreditBureauMCPServer().serve(port=port)
