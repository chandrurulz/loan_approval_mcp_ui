"""
agents/compliance_agent.py
============================
Agent: ComplianceAgent
Weight: 5%
MCP Server: compliance-mcp

Responsibilities:
  - KYC/CKYC verification status
  - AML screening and transaction monitoring
  - Sanctions screening (OFAC, UN, EU, India MEL)
  - PEP (Politically Exposed Person) detection
  - Adverse media and court records check
  - RBI defaulter list check

Scoring rules:
  Start at 100, deductions:
    Any sanctions hit         → score = 0 + SANCTIONS_HIT (hard stop)
    RBI defaulter list        → score = 0 + RBI_DEFAULTER (hard stop)
    AML status FLAGGED        → -40 + AML_FLAGGED
    AML risk HIGH             → -30 + HIGH_AML_RISK
    PEP detected              → -40 + PEP_DETECTED (requires EDD)
    Adverse media             → -20 + ADVERSE_MEDIA
    Court records             → -15 + COURT_RECORDS
    Regulatory action         → -20 + REGULATORY_ACTION
    KYC incomplete            → -15 + INCOMPLETE_KYC
    vKYC not done             → -5
"""

from __future__ import annotations

from agents.base import BaseAgent
from core.models import CustomerApplication, MCPToolCall
from config.settings import settings


class ComplianceAgent(BaseAgent):
    name   = "ComplianceAgent"
    weight = 0.05

    def __init__(self):
        self.mcp_url = settings.COMPLIANCE_MCP_URL

    def _build_tool_call(self, app: CustomerApplication) -> MCPToolCall:
        return MCPToolCall(
            tool       = "full_compliance",
            session_id = app.session_id,
            params     = {
                "customer_name":  app.customer_name,
                "pan_number":     app.pan_number,
                "aadhaar_number": app.aadhaar_number,
                "date_of_birth":  app.date_of_birth,
                "mobile":         app.mobile,
                "email":          app.email,
                "nationality":    "INDIAN",
            },
        )

    def _score(self, app: CustomerApplication, data: dict) -> tuple[float, list[str]]:
        score = 100.0
        flags = []

        # Hard stops
        sanctions = (data.get("sanctions_hit", False) or
                     data.get("ofac_hit", False) or
                     data.get("un_sanctions_hit", False))
        if sanctions:
            flags.append("SANCTIONS_HIT")
            return 0.0, flags

        if data.get("rbi_defaulter_list", False):
            flags.append("RBI_DEFAULTER")
            return 0.0, flags

        # AML
        if data.get("aml_status") == "FLAGGED":
            score -= 40
            flags.append("AML_FLAGGED")
        elif data.get("aml_risk_rating") == "HIGH":
            score -= 30
            flags.append("HIGH_AML_RISK")
        elif data.get("aml_risk_rating") == "MEDIUM":
            score -= 10

        # PEP
        if data.get("pep_flag", False):
            score -= 40
            flags.append("PEP_DETECTED")

        # Adverse media
        if data.get("adverse_media", False):
            score -= 20
            flags.append("ADVERSE_MEDIA")

        # Court / regulatory
        if data.get("court_records", False):
            score -= 15
            flags.append("COURT_RECORDS")
        if data.get("regulatory_actions", False):
            score -= 20
            flags.append("REGULATORY_ACTION")

        # KYC completeness
        if data.get("kyc_status") != "COMPLETE":
            score -= 15
            flags.append("INCOMPLETE_KYC")
        elif not data.get("vkyc_completed", True):
            score -= 5

        return score, flags
