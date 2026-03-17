#!/usr/bin/env python3
"""
mcp_health_check.py
====================
Checks all 5 MCP servers are running and responding correctly over HTTP.

Each check:
  1. GET  /health   → confirms the server is up and reports its mode
  2. POST /call     → fires a real probe tool call, validates the response shape

Usage:
  # Check all servers
  python3 mcp_health_check.py

  # Check one server by partial name
  python3 mcp_health_check.py --server credit

  # JSON output (for CI pipelines — exit 0 = healthy, 1 = unhealthy)
  python3 mcp_health_check.py --json

  # Custom timeout
  python3 mcp_health_check.py --timeout 3

Note: MCP servers must be running first:
  MOCK_DATA=true python3 mcp_servers/run_servers.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("MOCK_DATA", "true")

import httpx
from config.settings import settings

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m";  BOLD   = "\033[1m"
GREEN  = "\033[32m"; RED    = "\033[31m"
YELLOW = "\033[33m"; CYAN   = "\033[36m"; DIM = "\033[2m"

def green(t):  return f"{GREEN}{t}{RESET}"
def red(t):    return f"{RED}{t}{RESET}"
def yellow(t): return f"{YELLOW}{t}{RESET}"
def cyan(t):   return f"{CYAN}{t}{RESET}"
def bold(t):   return f"{BOLD}{t}{RESET}"
def dim(t):    return f"{DIM}{t}{RESET}"

# ── Health check registry ────────────────────────────────────────────────────

HEALTH_CHECKS = [
    {
        "name":    "document-verification-mcp",
        "label":   "Document Verification",
        "url":     settings.DOC_MCP_URL,
        "probe":   {"tool": "verify_pan", "params": {"pan_number": "ABCDE1234F", "customer_name": "Health Check"}},
        "validate": lambda d: ("pan_status" in d, f"pan_status={d.get('pan_status','MISSING')}"),
        "sources": ["NSDL PAN API", "UIDAI eKYC", "DigiLocker"],
    },
    {
        "name":    "credit-bureau-mcp",
        "label":   "Credit Bureau",
        "url":     settings.CREDIT_MCP_URL,
        "probe":   {"tool": "get_credit_score", "params": {"pan_number": "ABCDE1234F", "customer_name": "Health Check"}},
        "validate": lambda d: ("credit_score" in d and isinstance(d["credit_score"], (int,float)),
                               f"credit_score={d.get('credit_score','MISSING')}"),
        "sources": ["CIBIL", "Experian India", "Equifax India"],
    },
    {
        "name":    "bank-statement-mcp",
        "label":   "Bank Statement / Income",
        "url":     settings.BANK_MCP_URL,
        "probe":   {"tool": "calculate_income", "params": {"pan_number": "ABCDE1234F", "account_number": "1234567890", "stated_monthly_income": 50000}},
        "validate": lambda d: ("verified_monthly_income" in d,
                               f"verified_income={d.get('verified_monthly_income','MISSING')}"),
        "sources": ["RBI Account Aggregator", "Perfios", "Finbox"],
    },
    {
        "name":    "risk-engine-mcp",
        "label":   "Risk Engine / Fraud",
        "url":     settings.RISK_MCP_URL,
        "probe":   {"tool": "assess_fraud_risk", "params": {"pan_number": "ABCDE1234F", "mobile": "9876543210", "email": "health@check.com", "ip_address": "1.2.3.4", "device_id": "hc-device"}},
        "validate": lambda d: ("fraud_score" in d and isinstance(d["fraud_score"], (int,float)),
                               f"fraud_score={d.get('fraud_score','MISSING')}"),
        "sources": ["Internal Fraud ML", "Hunter.io", "Blacklist DB"],
    },
    {
        "name":    "compliance-mcp",
        "label":   "Compliance / AML",
        "url":     settings.COMPLIANCE_MCP_URL,
        "probe":   {"tool": "aml_screening", "params": {"pan_number": "ABCDE1234F", "customer_name": "Health Check", "date_of_birth": "1990-01-01"}},
        "validate": lambda d: ("aml_status" in d, f"aml_status={d.get('aml_status','MISSING')}"),
        "sources": ["FATF", "OFAC SDN", "WorldCheck", "RBI CRILC"],
    },
]


# ── Single server check ───────────────────────────────────────────────────────

async def check_one(chk: dict, timeout: float) -> dict:
    base_url = chk["url"]
    result = {
        "server":   chk["name"],
        "label":    chk["label"],
        "url":      base_url,
        "status":   "unknown",
        "mode":     "unknown",
        "latency_ms": None,
        "detail":   "",
        "sources":  chk["sources"],
    }

    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:

            # ── Step 1: GET /health ────────────────────────────────────────
            try:
                hr = await client.get(f"{base_url}/health")
                hr.raise_for_status()
                health_data   = hr.json()
                result["mode"] = health_data.get("mode", "unknown")
            except httpx.ConnectError:
                result["status"] = "unreachable"
                result["detail"] = f"Connection refused at {base_url} — is the server running?"
                result["detail"] += f"\n           Run: MOCK_DATA=true python3 mcp_servers/run_servers.py"
                return result
            except Exception as e:
                result["status"] = "error"
                result["detail"] = f"GET /health failed: {e}"
                return result

            # ── Step 2: POST /call with probe ─────────────────────────────
            cr = await client.post(f"{base_url}/call", json=chk["probe"])
            cr.raise_for_status()
            call_data = cr.json()

        latency = int((time.perf_counter() - start) * 1000)
        result["latency_ms"] = latency

        if not call_data.get("success"):
            result["status"] = "error"
            result["detail"] = f"MCP call failed: {call_data.get('error', 'unknown')}"
            return result

        ok, detail = chk["validate"](call_data.get("data", {}))
        result["status"] = "healthy" if ok else "degraded"
        result["detail"] = detail

    except asyncio.TimeoutError:
        result["status"]     = "timeout"
        result["latency_ms"] = int(timeout * 1000)
        result["detail"]     = f"No response within {timeout}s"
    except Exception as e:
        result["status"]     = "error"
        result["latency_ms"] = int((time.perf_counter() - start) * 1000)
        result["detail"]     = str(e)

    return result


# ── Run all ───────────────────────────────────────────────────────────────────

async def run_all(filter_name: str | None, timeout: float) -> list[dict]:
    checks = HEALTH_CHECKS
    if filter_name:
        checks = [c for c in checks if filter_name.lower() in c["name"].lower()]
        if not checks:
            print(red(f"\nNo server matching '{filter_name}'."))
            print(f"Available: {', '.join(c['name'] for c in HEALTH_CHECKS)}\n")
            sys.exit(1)
    return await asyncio.gather(*[check_one(c, timeout) for c in checks])


# ── CLI output ────────────────────────────────────────────────────────────────

STATUS_ICON = {
    "healthy":     green("●  HEALTHY     "),
    "degraded":    yellow("●  DEGRADED    "),
    "error":       red("●  ERROR       "),
    "timeout":     red("●  TIMEOUT     "),
    "unreachable": red("●  UNREACHABLE "),
    "unknown":     dim("●  UNKNOWN     "),
}

def print_results(results: list[dict]):
    sep  = "═" * 72
    sep2 = "─" * 72

    healthy = sum(1 for r in results if r["status"] == "healthy")
    total   = len(results)

    print(f"\n{bold(sep)}")
    print(f"  {bold(cyan('MCP Server Health Check'))}  {dim('(real HTTP endpoints)')}")
    print(sep2)

    for r in results:
        icon    = STATUS_ICON.get(r["status"], dim("● UNKNOWN"))
        latency = f"{r['latency_ms']}ms" if r["latency_ms"] is not None else "—"
        mode_str = dim(f"[{r['mode']}]") if r["mode"] != "unknown" else ""

        print(f"  {icon}  {bold(r['label']):<28}  {dim(latency):>8}  {mode_str}")
        print(f"           {dim(r['server'])}  →  {dim(r['url'])}")
        print(f"           {dim('Sources: ' + ', '.join(r['sources']))}")

        if r["detail"]:
            col = green if r["status"] == "healthy" else yellow if r["status"] == "degraded" else red
            for line in r["detail"].split("\n"):
                print(f"           {col(line)}")
        print()

    print(sep2)
    summary_col = green if healthy == total else red
    print(f"  {bold('Result:')}  {summary_col(f'{healthy}/{total} servers healthy')}")

    if healthy < total:
        unreachable = [r for r in results if r["status"] == "unreachable"]
        if unreachable:
            print(f"\n  {yellow('Start the servers first:')}")
            print(f"    MOCK_DATA=true python3 mcp_servers/run_servers.py")

    print(sep)

    if healthy == total:
        print(f"\n  {green('✅  All servers healthy and responding.')}")
    else:
        print(f"\n  {red('❌  Some servers are not responding.')}")
    print()


def print_json(results: list[dict]):
    out = {
        "overall": "healthy" if all(r["status"] == "healthy" for r in results) else "unhealthy",
        "servers": results,
    }
    print(json.dumps(out, indent=2))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MCP Server health check (HTTP)")
    parser.add_argument("--server",  "-s", help="Partial server name filter")
    parser.add_argument("--timeout", "-t", type=float, default=5.0, help="Timeout per server (default: 5)")
    parser.add_argument("--json",    "-j", action="store_true",     help="JSON output")
    args = parser.parse_args()

    results = asyncio.run(run_all(args.server, args.timeout))

    if args.json:
        print_json(results)
    else:
        print_results(results)

    sys.exit(0 if all(r["status"] == "healthy" for r in results) else 1)


if __name__ == "__main__":
    main()
