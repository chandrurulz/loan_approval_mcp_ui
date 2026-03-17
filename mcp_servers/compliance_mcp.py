"""
mcp_servers/compliance_mcp.py
===============================
MCP Server: compliance-mcp

Real integrations (MOCK_DATA=false):
  - RBI CRILC / SMA Database   → Central Repository of Information on Large Credits
  - FATF                       → Financial Action Task Force lists
  - OFAC SDN List              → US Office of Foreign Assets Control
  - UN Consolidated Sanctions  → United Nations sanctions list
  - WorldCheck (Refinitiv)     → PEP, Adverse Media, Sanctions
  - CRZ / SARFAESI DBs         → Indian NPA/recovery proceedings

Tools exposed:
  - kyc_check         → Know Your Customer verification
  - aml_screening     → Anti-Money Laundering check
  - sanctions_check   → Multi-list sanctions screening
  - pep_check         → Politically Exposed Person check
  - adverse_media     → Negative news screening
  - full_compliance   → All checks combined

Mock behaviour:
  - Customer name starting with 'Z'  → PEP_DETECTED
  - Mobile starting '0000'           → AML_HIGH_RISK
  - Normal inputs                    → All clear
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Any, Dict

from mcp_servers.base import BaseMCPServer
from core.models import MCPToolCall


class ComplianceMCPServer(BaseMCPServer):
    server_name = "compliance-mcp"

    async def _mock_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        tool = tool_call.tool
        p    = tool_call.params

        if tool == "kyc_check":
            return self._build_kyc(p)
        elif tool == "aml_screening":
            return self._build_aml(p)
        elif tool == "sanctions_check":
            return self._build_sanctions(p)
        elif tool == "pep_check":
            return self._build_pep(p)
        elif tool == "adverse_media":
            return self._build_adverse_media(p)
        elif tool in ("full_compliance", "full_compliance_check"):
            kyc  = self._build_kyc(p)
            aml  = self._build_aml(p)
            sanc = self._build_sanctions(p)
            pep  = self._build_pep(p)
            med  = self._build_adverse_media(p)
            return {**kyc, **aml, **sanc, **pep, **med,
                    "compliance_ref": f"COMP-{uuid.uuid4().hex[:10].upper()}",
                    "screened_at": datetime.now().isoformat()}
        else:
            raise ValueError(f"Unknown tool: {tool}")

    # ── Builders ──────────────────────────────────────────────────────────

    def _build_kyc(self, p: dict) -> Dict[str, Any]:
        return {
            "kyc_status":     "COMPLETE",
            "kyc_level":      "FULL_KYC",
            "kyc_type":       "DIGITAL_KYC",
            "ckyc_number":    f"CKYC-{uuid.uuid4().hex[:12].upper()}",
            "ckyc_registered": True,
            "vkyc_completed": True,
            "kyc_expiry":     "2027-12-31",
        }

    def _build_aml(self, p: dict) -> Dict[str, Any]:
        mobile    = p.get("mobile", "9999999999")
        high_risk = mobile.startswith("0000")
        seed      = self._seed(p.get("pan_number", ""), p.get("customer_name", ""))
        rng       = random.Random(seed)

        return {
            "aml_status":         "FLAGGED" if high_risk else "CLEAR",
            "aml_risk_rating":    "HIGH" if high_risk else rng.choice(["LOW", "LOW", "LOW", "MEDIUM"]),
            "transaction_monitoring": {
                "unusual_patterns":     high_risk,
                "cash_intensive":       False,
                "round_tripping":       False,
                "structuring_suspected": False,
            },
            "fiu_ind_registered": not high_risk,
            "aml_check_ref":      f"AML-{uuid.uuid4().hex[:8].upper()}",
        }

    def _build_sanctions(self, p: dict) -> Dict[str, Any]:
        pan = p.get("pan_number", "ABCDE1234F")
        hit = pan.upper().startswith("FAKE")

        return {
            "sanctions_hit":      hit,
            "ofac_hit":           False,
            "un_sanctions_hit":   False,
            "eu_sanctions_hit":   False,
            "india_mel_hit":      False,  # Ministry of External Affairs list
            "rbi_caution_list":   False,
            "sanctions_lists_checked": ["OFAC_SDN", "UN_CONSOLIDATED", "EU_FINANCIAL", "INDIA_MEL"],
            "sanctions_check_ref": f"SANC-{uuid.uuid4().hex[:8].upper()}",
        }

    def _build_pep(self, p: dict) -> Dict[str, Any]:
        name    = p.get("customer_name", "")
        is_pep  = name.upper().startswith("Z")
        seed    = self._seed(name)
        rng     = random.Random(seed)

        pep_category = rng.choice([
            "NATIONAL_POLITICIAN", "SENIOR_GOVERNMENT_OFFICIAL",
            "SENIOR_MILITARY_OFFICIAL", "JUDICIAL_OFFICIAL",
        ]) if is_pep else None

        return {
            "pep_flag":         is_pep,
            "pep_category":     pep_category,
            "pep_country":      "INDIA" if is_pep else None,
            "pep_status":       "CURRENT" if is_pep else None,
            "close_associate":  False,
            "family_member":    False,
            "enhanced_due_diligence_required": is_pep,
            "pep_check_ref":    f"PEP-{uuid.uuid4().hex[:8].upper()}",
        }

    def _build_adverse_media(self, p: dict) -> Dict[str, Any]:
        name       = p.get("customer_name", "")
        is_adverse = name.upper().startswith("X")
        seed       = self._seed(name)
        rng        = random.Random(seed)

        return {
            "adverse_media":           is_adverse,
            "adverse_media_categories": ["FRAUD", "FINANCIAL_CRIME"] if is_adverse else [],
            "news_articles_found":     rng.randint(2, 8) if is_adverse else 0,
            "court_records":           False,
            "regulatory_actions":      False,
            "rbi_defaulter_list":      False,
            "sarfaesi_proceedings":    False,
            "media_check_ref":         f"MED-{uuid.uuid4().hex[:8].upper()}",
        }

    async def _real_response(self, tool_call: MCPToolCall) -> dict:
        """Production: call real FATF/OFAC/WorldCheck APIs."""
        raise NotImplementedError("Implement real compliance API integration here.")

    def tools(self):
        return ["kyc_check", "aml_screening", "sanctions_check", "pep_check"]

if __name__ == "__main__":
    import os
    port = int(os.environ.get("COMPLIANCE_MCP_PORT", 8005))
    print(f"Starting compliance-mcp on port {port}  [mock={os.environ.get('MOCK_DATA','true')}]")
    ComplianceMCPServer().serve(port=port)
