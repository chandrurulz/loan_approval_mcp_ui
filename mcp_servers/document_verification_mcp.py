"""
mcp_servers/document_verification_mcp.py
=========================================
MCP Server: document-verification-mcp

Real integrations (MOCK_DATA=false):
  - UIDAI eKYC API          → Aadhaar verification
  - NSDL PAN Verification   → PAN card validation
  - DigiLocker Gateway      → Fetched issued documents
  - OCR Engine              → Document authenticity scoring

Tools exposed:
  - verify_pan       → Validate PAN against NSDL
  - verify_aadhaar   → Validate Aadhaar via UIDAI
  - verify_documents → Check uploaded doc authenticity

Mock behaviour:
  - PAN starting with 'FAKE' → PAN_INVALID
  - Aadhaar starting with '0000' → AADHAAR_UNVERIFIED
  - Normal PAN/Aadhaar → all verified
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict

from mcp_servers.base import BaseMCPServer
from core.models import MCPToolCall


class DocumentVerificationMCPServer(BaseMCPServer):
    server_name = "document-verification-mcp"

    # ── Tool Router ────────────────────────────────────────────────────────

    async def _mock_response(self, tool_call: MCPToolCall) -> Dict[str, Any]:
        tool = tool_call.tool
        p    = tool_call.params

        if tool == "verify_pan":
            return await self._mock_verify_pan(p)
        elif tool == "verify_aadhaar":
            return await self._mock_verify_aadhaar(p)
        elif tool == "verify_documents":
            return await self._mock_verify_documents(p)
        elif tool == "verify_all":
            pan_r  = await self._mock_verify_pan(p)
            aad_r  = await self._mock_verify_aadhaar(p)
            doc_r  = await self._mock_verify_documents(p)
            return {**pan_r, **aad_r, **doc_r, "overall_status": self._overall(pan_r, aad_r, doc_r)}
        else:
            raise ValueError(f"Unknown tool: {tool}")

    # ── Individual Mock Tools ──────────────────────────────────────────────

    async def _mock_verify_pan(self, p: dict) -> Dict[str, Any]:
        pan = p.get("pan_number", "ABCDE1234F")

        if pan.upper().startswith("FAKE"):
            return {
                "pan_valid": False,
                "pan_status": "NOT_FOUND",
                "error": "PAN not found in NSDL database",
                "verification_id": f"PAN-ERR-{uuid.uuid4().hex[:6].upper()}",
            }

        seed = self._seed(pan)
        name_match = (seed % 10) > 1   # 80% match rate

        return {
            "pan_valid": True,
            "pan_status": "ACTIVE",
            "name_match": name_match,
            "name_on_pan": p.get("customer_name", ""),
            "dob_match": True,
            "issued_by": "Income Tax Department of India",
            "pan_type": "Individual",
            "linked_aadhaar": True,
            "verification_id": f"PAN-{uuid.uuid4().hex[:8].upper()}",
            "verified_at": datetime.now().isoformat(),
        }

    async def _mock_verify_aadhaar(self, p: dict) -> Dict[str, Any]:
        aadhaar = p.get("aadhaar_number", "9999-9999-9999").replace("-", "").replace(" ", "")

        if aadhaar.startswith("0000"):
            return {
                "aadhaar_verified": False,
                "aadhaar_status": "INVALID",
                "error": "Aadhaar number not found in UIDAI",
                "verification_id": f"AAD-ERR-{uuid.uuid4().hex[:6].upper()}",
            }

        return {
            "aadhaar_verified": True,
            "aadhaar_status": "ACTIVE",
            "name_match": True,
            "address_match": True,
            "mobile_linked": True,
            "biometric_consent": True,
            "e_kyc_level": "OTP",
            "uid_token": f"UID-{uuid.uuid4().hex[:12].upper()}",
            "verification_id": f"AAD-{uuid.uuid4().hex[:8].upper()}",
            "verified_at": datetime.now().isoformat(),
        }

    async def _mock_verify_documents(self, p: dict) -> Dict[str, Any]:
        seed = self._seed(p.get("pan_number", ""), p.get("customer_name", ""))
        quality_score = 85 + (seed % 15)

        return {
            "documents": {
                "salary_slip": {
                    "uploaded": True,
                    "authentic": True,
                    "months_covered": 3,
                    "employer_name_match": True,
                    "tamper_detected": False,
                    "ocr_confidence": round(0.92 + (seed % 8) / 100, 2),
                },
                "bank_statement": {
                    "uploaded": True,
                    "authentic": True,
                    "months_covered": 6,
                    "account_number_verified": True,
                    "tamper_detected": False,
                    "ocr_confidence": round(0.94 + (seed % 6) / 100, 2),
                },
                "address_proof": {
                    "uploaded": True,
                    "authentic": True,
                    "type": "utility_bill",
                    "address_match": True,
                    "tamper_detected": False,
                },
                "photo_id": {
                    "uploaded": True,
                    "face_match_score": round(0.88 + (seed % 11) / 100, 2),
                    "liveness_check": "PASS",
                },
            },
            "overall_doc_quality_score": quality_score,
            "total_docs_submitted": 4,
            "docs_verified": 4,
            "digilocker_consent": True,
            "doc_verification_ref": f"DOC-{uuid.uuid4().hex[:10].upper()}",
        }

    def _overall(self, pan_r: dict, aad_r: dict, doc_r: dict) -> str:
        if pan_r.get("pan_valid") and aad_r.get("aadhaar_verified"):
            return "VERIFIED"
        elif pan_r.get("pan_valid") or aad_r.get("aadhaar_verified"):
            return "PARTIAL"
        return "FAILED"

    async def _real_response(self, tool_call: MCPToolCall) -> dict:
        """
        Production: call real NSDL/UIDAI/DigiLocker APIs.
        Set DOC_MCP_URL to point agents to this running server.
        """
        raise NotImplementedError("Implement real NSDL/UIDAI integration here.")

    def tools(self):
        return ["verify_pan", "verify_aadhaar", "verify_documents", "verify_all"]

    # ── Entry point for standalone server ─────────────────────────────────

if __name__ == "__main__":
    import os
    port = int(os.environ.get("DOC_MCP_PORT", 8001))
    print(f"Starting document-verification-mcp on port {port}  [mock={os.environ.get('MOCK_DATA','true')}]")
    DocumentVerificationMCPServer().serve(port=port)
