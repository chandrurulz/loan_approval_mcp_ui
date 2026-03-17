"""
agents/risk_assessment_agent.py
=================================
Agent: RiskAssessmentAgent
Weight: 15%
MCP Server: risk-engine-mcp

Responsibilities:
  - Fraud signal scoring via ML models
  - Device & IP intelligence
  - Mobile / email reputation check
  - Application velocity (rate limiting)
  - Synthetic identity detection
  - Blacklist / debarment check

Scoring rules:
  Base = fraud_score from MCP (0–100, higher=cleaner)
  Deductions:
    Blacklist hit               → score = 0  + BLACKLIST_HIT
    Risk band CRITICAL          → -40 + FRAUD_RISK_CRITICAL
    Risk band HIGH              → -20 + HIGH_FRAUD_RISK
    Velocity ≥ 3 apps/30d       → -20 + VELOCITY_BREACH
    Synthetic score > 0.5       → -30 + SYNTHETIC_IDENTITY_SUSPECT
    VPN detected                → -10 + VPN_DETECTED
    Disposable email            → -8 + DISPOSABLE_EMAIL
    IP reputation BAD           → -10 + BAD_IP_REPUTATION
    Emulator detected           → -15 + EMULATOR_DETECTED
"""

from __future__ import annotations

from agents.base import BaseAgent
from core.models import CustomerApplication, MCPToolCall
from config.settings import settings


class RiskAssessmentAgent(BaseAgent):
    name   = "RiskAssessmentAgent"
    weight = 0.15

    def __init__(self):
        self.mcp_url = settings.RISK_MCP_URL

    def _build_tool_call(self, app: CustomerApplication) -> MCPToolCall:
        return MCPToolCall(
            tool       = "full_risk_check",
            session_id = app.session_id,
            params     = {
                "pan_number":    app.pan_number,
                "customer_name": app.customer_name,
                "mobile":        app.mobile,
                "email":         app.email,
                "ip_address":    app.ip_address,
                "device_id":     app.device_id,
                "loan_amount":   app.loan_amount,
            },
        )

    def _score(self, app: CustomerApplication, data: dict) -> tuple[float, list[str]]:
        score = data.get("fraud_score", 80.0)
        flags = []

        # Hard stop: blacklist
        if data.get("blacklist_hit", False):
            flags.append("BLACKLIST_HIT")
            return 0.0, flags

        # Risk band
        risk_band = data.get("risk_band", "LOW")
        if risk_band == "CRITICAL":
            score -= 40
            flags.append("FRAUD_RISK_CRITICAL")
        elif risk_band == "HIGH":
            score -= 20
            flags.append("HIGH_FRAUD_RISK")

        # Velocity
        velocity = data.get("velocity", {})
        if velocity.get("applications_last_30d", 0) >= 3:
            score -= 20
            flags.append("VELOCITY_BREACH")

        # Synthetic identity
        if data.get("synthetic_identity_score", 0) > 0.5:
            score -= 30
            flags.append("SYNTHETIC_IDENTITY_SUSPECT")

        # Device intelligence
        device = data.get("device_intelligence", {})
        if device.get("vpn_detected", False):
            score -= 10
            flags.append("VPN_DETECTED")
        if device.get("emulator_detected", False):
            score -= 15
            flags.append("EMULATOR_DETECTED")
        if device.get("ip_reputation") == "BAD":
            score -= 10
            flags.append("BAD_IP_REPUTATION")

        # Email reputation
        email_rep = data.get("email_reputation", {})
        if email_rep.get("disposable_email", False):
            score -= 8
            flags.append("DISPOSABLE_EMAIL")
        if email_rep.get("breach_detected", False):
            score -= 5

        # Mobile reputation
        mobile_rep = data.get("mobile_reputation", {})
        if mobile_rep.get("reported_fraud", False):
            score -= 15
            flags.append("MOBILE_FRAUD_REPORTED")

        return score, flags
