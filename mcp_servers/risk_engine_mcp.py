"""
mcp_servers/risk_engine_mcp.py
================================
MCP Server: risk-engine-mcp

Real integrations (MOCK_DATA=false):
  - Internal ML Risk Models  → Fraud probability scoring
  - Hunter.io                → Email/mobile reputation
  - Device Intelligence      → Device fingerprint & IP analysis
  - Bureau Velocity          → Cross-bureau application velocity
  - Internal Blacklist DB    → Known defaulters

Tools exposed:
  - assess_fraud_risk   → Fraud signal scoring (0–100, higher = cleaner)
  - check_blacklist     → Defaulter / debarment list lookup
  - get_risk_band       → Final risk band: LOW / MEDIUM / HIGH / CRITICAL

Mock behaviour:
  - Mobile starting '0000'      → BLACKLIST_HIT
  - Email ending '@fraud.com'   → HIGH_FRAUD_RISK
  - Normal inputs               → LOW–MEDIUM risk band
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Any, Dict

from mcp_servers.base import BaseMCPServer
from core.models import MCPToolCall


class RiskEngineMCPServer(BaseMCPServer):
    server_name = "risk-engine-mcp"

    async def _mock_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        tool = tool_call.tool
        p    = tool_call.params

        if tool == "assess_fraud_risk":
            return self._build_fraud_assessment(p)
        elif tool == "check_blacklist":
            return self._build_blacklist_check(p)
        elif tool == "get_risk_band":
            fraud = self._build_fraud_assessment(p)
            blist = self._build_blacklist_check(p)
            return {**fraud, **blist}
        elif tool == "full_risk_check":
            fraud = self._build_fraud_assessment(p)
            blist = self._build_blacklist_check(p)
            return {**fraud, **blist}
        else:
            raise ValueError(f"Unknown tool: {tool}")

    # ── Builders ──────────────────────────────────────────────────────────

    def _build_fraud_assessment(self, p: dict) -> Dict[str, Any]:
        mobile = p.get("mobile", "9999999999")
        email  = p.get("email", "user@example.com")
        seed   = self._seed(mobile, email)
        rng    = random.Random(seed)

        # Forced fraud scenarios
        is_fraud_mobile = mobile.startswith("0000")
        is_fraud_email  = email.endswith("@fraud.com")
        is_fraud        = is_fraud_mobile or is_fraud_email

        if is_fraud:
            fraud_score = rng.uniform(5, 25)
        else:
            fraud_score = rng.uniform(72, 98)

        velocity_apps = rng.randint(3, 6) if is_fraud else rng.randint(0, 2)

        return {
            "fraud_score":               round(fraud_score, 1),
            "risk_band":                 self._risk_band(fraud_score),
            "mobile_reputation": {
                "age_months":            rng.randint(2, 18) if is_fraud else rng.randint(18, 120),
                "reported_fraud":        is_fraud_mobile,
                "carrier":               "Unknown" if is_fraud_mobile else rng.choice(["Jio", "Airtel", "Vi", "BSNL"]),
                "number_type":           "PREPAID" if is_fraud_mobile else rng.choice(["POSTPAID", "PREPAID"]),
            },
            "email_reputation": {
                "age_months":            rng.randint(1, 6) if is_fraud_email else rng.randint(12, 96),
                "domain_reputation":     "POOR" if is_fraud_email else "GOOD",
                "disposable_email":      is_fraud_email,
                "breach_detected":       is_fraud_email,
            },
            "device_intelligence": {
                "device_fingerprint_match": not is_fraud,
                "ip_reputation":         "BAD" if is_fraud else "CLEAN",
                "vpn_detected":          is_fraud,
                "emulator_detected":     is_fraud,
                "location_mismatch":     is_fraud,
            },
            "velocity": {
                "applications_last_30d": velocity_apps,
                "applications_last_90d": velocity_apps + rng.randint(0, 2),
                "rejections_last_90d":   velocity_apps - 1 if velocity_apps > 0 else 0,
            },
            "synthetic_identity_score":  round(rng.uniform(0.55, 0.85) if is_fraud else rng.uniform(0.01, 0.08), 3),
            "social_score":              round(rng.uniform(20, 50) if is_fraud else rng.uniform(65, 95), 1),
            "risk_model_version":        "v3.2.1",
            "assessment_id":             f"RISK-{uuid.uuid4().hex[:10].upper()}",
            "assessed_at":               datetime.now().isoformat(),
        }

    def _build_blacklist_check(self, p: dict) -> Dict[str, Any]:
        mobile = p.get("mobile", "9999999999")
        pan    = p.get("pan_number", "ABCDE1234F")

        blacklisted = mobile.startswith("0000") or pan.upper().startswith("FAKE")

        return {
            "blacklist_hit":        blacklisted,
            "pan_blacklisted":      pan.upper().startswith("FAKE"),
            "mobile_blacklisted":   mobile.startswith("0000"),
            "rbi_wilful_defaulter": False,
            "sebi_debarred":        False,
            "court_order_active":   False,
            "blacklist_source":     "INTERNAL_DB v2024.11" if blacklisted else None,
            "check_id":             f"BL-{uuid.uuid4().hex[:8].upper()}",
        }

    @staticmethod
    def _risk_band(score: float) -> str:
        if score >= 80: return "LOW"
        if score >= 60: return "MEDIUM"
        if score >= 35: return "HIGH"
        return "CRITICAL"

    async def _real_response(self, tool_call: MCPToolCall) -> dict:
        """Production: call real fraud ML / blacklist APIs."""
        raise NotImplementedError("Implement real fraud ML integration here.")

    def tools(self):
        return ["assess_fraud_risk", "check_blacklist", "get_risk_band", "full_risk_check"]

if __name__ == "__main__":
    import os
    port = int(os.environ.get("RISK_MCP_PORT", 8004))
    print(f"Starting risk-engine-mcp on port {port}  [mock={os.environ.get('MOCK_DATA','true')}]")
    RiskEngineMCPServer().serve(port=port)
