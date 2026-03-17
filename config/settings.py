"""config/settings.py"""
import os

class Settings:
    MOCK_DATA           = os.environ.get("MOCK_DATA", "true").lower() == "true"
    API_HOST            = os.environ.get("API_HOST", "0.0.0.0")
    API_PORT            = int(os.environ.get("API_PORT", "8000"))
    AGENT_TIMEOUT       = float(os.environ.get("AGENT_TIMEOUT", "10.0"))
    APPROVE_THRESHOLD   = float(os.environ.get("APPROVE_THRESHOLD", "70.0"))
    REFER_THRESHOLD     = float(os.environ.get("REFER_THRESHOLD", "50.0"))
    WEIGHT_CREDIT       = 0.35
    WEIGHT_INCOME       = 0.25
    WEIGHT_DOCS         = 0.20
    WEIGHT_RISK         = 0.15
    WEIGHT_COMPLIANCE   = 0.05
    RATE_BANDS          = [(90, 9.5), (85, 10.0), (80, 10.5), (75, 11.0), (70, 12.0)]
    PROCESSING_FEE_PCT  = 0.01

    # ── MCP Server URLs ────────────────────────────────────────────────────
    # Each MCP server runs as a real HTTP service on its own port.
    # Override these via environment variables to point to remote servers.
    DOC_MCP_URL        = os.environ.get("DOC_MCP_URL",        "http://localhost:8001")
    CREDIT_MCP_URL     = os.environ.get("CREDIT_MCP_URL",     "http://localhost:8002")
    BANK_MCP_URL       = os.environ.get("BANK_MCP_URL",       "http://localhost:8003")
    RISK_MCP_URL       = os.environ.get("RISK_MCP_URL",       "http://localhost:8004")
    COMPLIANCE_MCP_URL = os.environ.get("COMPLIANCE_MCP_URL", "http://localhost:8005")

settings = Settings()
