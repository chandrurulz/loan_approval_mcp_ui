#!/usr/bin/env python3
"""
app_server.py
=============
Starts the Loan Approval API on port 8000.

Usage:
  # Terminal 1 — MCP servers
  MOCK_DATA=true python3 mcp_servers/run_servers.py

  # Terminal 2 — API server
  MOCK_DATA=true python3 app_server.py

  # Then open loan_application_ui.html in your browser
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("MOCK_DATA", "true")

import uvicorn
from api.gateway import app

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", 8000))
    mock = os.environ.get("MOCK_DATA", "true")
    print(f"\n  Loan Approval API  →  http://localhost:{port}")
    print(f"  Swagger docs       →  http://localhost:{port}/docs")
    print(f"  MOCK_DATA          →  {mock}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
