#!/usr/bin/env python3
"""
mcp_servers/run_servers.py
===========================
Starts all 5 MCP servers as real HTTP microservices.

Each server runs in its own thread on its own port:
  document-verification-mcp  → http://localhost:8001
  credit-bureau-mcp          → http://localhost:8002
  bank-statement-mcp         → http://localhost:8003
  risk-engine-mcp            → http://localhost:8004
  compliance-mcp             → http://localhost:8005

When MOCK_DATA=true  → each server responds with deterministic mock data
When MOCK_DATA=false → each server calls its real external API

Usage:
  # Start all servers (mock mode)
  MOCK_DATA=true python3 mcp_servers/run_servers.py

  # Start all servers (real API mode)
  MOCK_DATA=false python3 mcp_servers/run_servers.py

  # Custom ports via env
  DOC_MCP_PORT=9001 CREDIT_MCP_PORT=9002 MOCK_DATA=true python3 mcp_servers/run_servers.py

  # Then in another terminal, run the pipeline:
  MOCK_DATA=true python3 main.py
  MOCK_DATA=true python3 langgraph_orchestrator/main_langgraph.py

  # Or check health:
  python3 mcp_health_check.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("MOCK_DATA", "true")

import uvicorn

from mcp_servers.document_verification_mcp import DocumentVerificationMCPServer
from mcp_servers.credit_bureau_mcp import CreditBureauMCPServer
from mcp_servers.bank_statement_mcp import BankStatementMCPServer
from mcp_servers.risk_engine_mcp import RiskEngineMCPServer
from mcp_servers.compliance_mcp import ComplianceMCPServer
from config.settings import settings

# ── ANSI colours ──────────────────────────────────────────────────────────────
BOLD  = "\033[1m"
CYAN  = "\033[36m"
GREEN = "\033[32m"
DIM   = "\033[2m"
RESET = "\033[0m"

# ── Server registry ───────────────────────────────────────────────────────────
SERVERS = [
    {
        "cls":      DocumentVerificationMCPServer,
        "port_env": "DOC_MCP_PORT",
        "default":  8001,
        "url_env":  "DOC_MCP_URL",
    },
    {
        "cls":      CreditBureauMCPServer,
        "port_env": "CREDIT_MCP_PORT",
        "default":  8002,
        "url_env":  "CREDIT_MCP_URL",
    },
    {
        "cls":      BankStatementMCPServer,
        "port_env": "BANK_MCP_PORT",
        "default":  8003,
        "url_env":  "BANK_MCP_URL",
    },
    {
        "cls":      RiskEngineMCPServer,
        "port_env": "RISK_MCP_PORT",
        "default":  8004,
        "url_env":  "RISK_MCP_URL",
    },
    {
        "cls":      ComplianceMCPServer,
        "port_env": "COMPLIANCE_MCP_PORT",
        "default":  8005,
        "url_env":  "COMPLIANCE_MCP_URL",
    },
]


def _start_server(cls, port: int):
    """Run a single MCP server in a blocking uvicorn loop (called in a thread)."""
    instance = cls()
    app      = instance._build_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def start_all():
    mode = f"{CYAN}MOCK{RESET}" if settings.MOCK_DATA else f"{GREEN}REAL API{RESET}"
    print(f"\n{BOLD}Starting MCP Servers{RESET}  [{mode}]\n")

    threads = []
    for srv in SERVERS:
        port     = int(os.environ.get(srv["port_env"], srv["default"]))
        instance = srv["cls"]()
        name     = instance.server_name

        # Set the URL env so agents pick it up automatically
        os.environ[srv["url_env"]] = f"http://localhost:{port}"

        t = threading.Thread(
            target=_start_server,
            args=(srv["cls"], port),
            daemon=True,       # dies when main process exits
            name=name,
        )
        t.start()
        threads.append((name, port, t))
        print(f"  {DIM}▶{RESET}  {BOLD}{name:<32}{RESET}  http://localhost:{port}")

    # Give servers a moment to bind their ports
    print(f"\n  Starting up", end="", flush=True)
    for _ in range(8):
        time.sleep(0.3)
        print(".", end="", flush=True)
    print(f"  {GREEN}ready{RESET}\n")

    print(f"  {DIM}Endpoints:{RESET}")
    for name, port, _ in threads:
        print(f"    POST http://localhost:{port}/call")
        print(f"    GET  http://localhost:{port}/health")
    print()

    return threads


def main():
    threads = start_all()

    print(f"  {BOLD}All servers running.{RESET}  Press Ctrl+C to stop.\n")
    print(f"  {DIM}Run the pipeline in another terminal:{RESET}")
    print(f"    MOCK_DATA=true python3 main.py")
    print(f"    MOCK_DATA=true python3 langgraph_orchestrator/main_langgraph.py")
    print(f"    python3 mcp_health_check.py\n")

    try:
        while True:
            time.sleep(1)
            dead = [name for name, _, t in threads if not t.is_alive()]
            if dead:
                print(f"\n  ⚠  Server(s) crashed: {', '.join(dead)}")
                print("  Restarting in 3s...")
                time.sleep(3)
                for srv in SERVERS:
                    inst = srv["cls"]()
                    if inst.server_name in dead:
                        port = int(os.environ.get(srv["port_env"], srv["default"]))
                        t = threading.Thread(
                            target=_start_server, args=(srv["cls"], port),
                            daemon=True, name=inst.server_name
                        )
                        t.start()
    except KeyboardInterrupt:
        print("\n\n  Shutting down MCP servers.\n")


if __name__ == "__main__":
    main()
