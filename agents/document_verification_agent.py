"""
agents/document_verification_agent.py
=======================================
Agent: DocumentVerificationAgent
Weight: 20%
MCP Server: document-verification-mcp

Responsibilities:
  - Verify PAN and Aadhaar are genuine and match applicant
  - Check uploaded documents (salary slip, bank statement, address proof)
  - Detect document tampering / OCR fraud
  - Ensure liveness / face match

Scoring rules:
  Start at 100, deduct points for each failure:
    PAN invalid              → -60 pts + flag PAN_INVALID
    Aadhaar unverified       → -30 pts + flag AADHAAR_UNVERIFIED
    Name mismatch on PAN     → -15 pts + flag PAN_NAME_MISMATCH
    Salary slip not authentic→ -20 pts + flag SALARY_SLIP_SUSPECT
    Bank stmt not authentic  → -15 pts + flag BANK_STMT_SUSPECT
    Tamper detected (any doc)→ -25 pts + flag DOCUMENT_TAMPERED
    Face match < 80%         → -10 pts + flag FACE_MATCH_LOW
    Liveness check failed    → -20 pts + flag LIVENESS_FAILED
"""

from __future__ import annotations

from agents.base import BaseAgent
from core.models import CustomerApplication, MCPToolCall
from config.settings import settings


class DocumentVerificationAgent(BaseAgent):
    name   = "DocumentVerificationAgent"
    weight = 0.20

    def __init__(self):
        self.mcp_url = settings.DOC_MCP_URL

    def _build_tool_call(self, app: CustomerApplication) -> MCPToolCall:
        return MCPToolCall(
            tool       = "verify_all",
            session_id = app.session_id,
            params     = {
                "pan_number":      app.pan_number,
                "aadhaar_number":  app.aadhaar_number,
                "customer_name":   app.customer_name,
                "date_of_birth":   app.date_of_birth,
                "mobile":          app.mobile,
            },
        )

    def _score(self, app: CustomerApplication, data: dict) -> tuple[float, list[str]]:
        score = 100.0
        flags = []

        # PAN validation
        if not data.get("pan_valid", False):
            score -= 60
            flags.append("PAN_INVALID")
        elif not data.get("name_match", True):
            score -= 15
            flags.append("PAN_NAME_MISMATCH")

        # Aadhaar validation
        if not data.get("aadhaar_verified", False):
            score -= 30
            flags.append("AADHAAR_UNVERIFIED")

        # Document checks
        docs = data.get("documents", {})

        salary = docs.get("salary_slip", {})
        if not salary.get("authentic", True):
            score -= 20
            flags.append("SALARY_SLIP_SUSPECT")
        if salary.get("tamper_detected", False):
            score -= 25
            flags.append("DOCUMENT_TAMPERED")

        bank_stmt = docs.get("bank_statement", {})
        if not bank_stmt.get("authentic", True):
            score -= 15
            flags.append("BANK_STMT_SUSPECT")

        photo = docs.get("photo_id", {})
        face_score = photo.get("face_match_score", 1.0)
        if face_score < 0.80:
            score -= 10
            flags.append("FACE_MATCH_LOW")
        if photo.get("liveness_check", "PASS") != "PASS":
            score -= 20
            flags.append("LIVENESS_FAILED")

        # Overall doc quality
        quality = data.get("overall_doc_quality_score", 80)
        if quality < 60:
            score -= 10
            flags.append("LOW_DOC_QUALITY")

        return score, flags
