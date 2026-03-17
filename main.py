#!/usr/bin/env python3
"""
main.py — Real-Time Loan Approval Multi-Agent Orchestration
Run: MOCK_DATA=true python main.py
"""
import asyncio, json, os, sys, uuid
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("MOCK_DATA", "true")

from agents.orchestrator import OrchestratorAgent
from core.models import CustomerApplication, Decision, LoanPurpose, EmploymentType
from config.settings import settings

# ─────────────────────────────────────────────────────────────────────────────
SEP = "═" * 70

def color(text, code): return f"\033[{code}m{text}\033[0m"
def bold(t):    return color(t, "1")
def cyan(t):    return color(t, "36")
def green(t):   return color(t, "32")
def yellow(t):  return color(t, "33")
def red(t):     return color(t, "31")
def dim(t):     return color(t, "2")

# ─────────────────────────────────────────────────────────────────────────────
TEST_CASES = [
    CustomerApplication(
        customer_name="Priya Sharma", pan_number="ABCPS1234P",
        aadhaar_number="9876-5432-1098", date_of_birth="1988-04-15",
        mobile="9876543210", email="priya.sharma@gmail.com",
        loan_amount=500_000, loan_tenure_months=36,
        loan_purpose=LoanPurpose.HOME_RENOVATION,
        monthly_income=85_000, employer_name="Tata Consultancy Services",
        employment_type=EmploymentType.SALARIED, years_of_employment=6.5,
        residential_address="42 MG Road, Bengaluru", city="Bengaluru", pincode="560001",
    ),
    CustomerApplication(
        customer_name="Zubair Ali Khan", pan_number="ZZXZA9999Z",
        aadhaar_number="1234-5678-9012", date_of_birth="1975-11-30",
        mobile="9123456780", email="zubair.khan@company.com",
        loan_amount=1_500_000, loan_tenure_months=60,
        loan_purpose=LoanPurpose.BUSINESS,
        monthly_income=180_000, employer_name="Self-Employed",
        employment_type=EmploymentType.SELF_EMPLOYED, years_of_employment=10.0,
        residential_address="15 Juhu Tara Road, Mumbai", city="Mumbai", pincode="400049",
    ),
    CustomerApplication(
        customer_name="Fraudster One", pan_number="FAKEX0000X",
        aadhaar_number="0000-0000-0001", date_of_birth="1990-01-01",
        mobile="0000000001", email="hacker@fraud.com",
        loan_amount=2_000_000, loan_tenure_months=24,
        monthly_income=10_000, employer_name="Unknown Corp",
        residential_address="Unknown", city="Unknown",
    ),
    CustomerApplication(
        customer_name="Rahul Mehta", pan_number="ABCRM5678M",
        aadhaar_number="5555-6666-7777", date_of_birth="1982-07-20",
        mobile="8765432190", email="rahul.mehta@infosys.com",
        loan_amount=3_000_000, loan_tenure_months=120,
        loan_purpose=LoanPurpose.HOME_PURCHASE,
        monthly_income=150_000, employer_name="Infosys Limited",
        employment_type=EmploymentType.SALARIED, years_of_employment=12.0,
        residential_address="78 Sector 15, Noida", city="Noida", pincode="201301",
    ),
]

def print_agent_row(r):
    s = r.score
    score_str = (green if s >= 70 else yellow if s >= 50 else red)(f"{s:5.1f}")
    status_str = (green("[PASS]") if r.status.value == "pass" else
                  red("[FAIL]")   if r.status.value == "fail" else yellow("[ERR ]"))
    flags_str = ", ".join(r.flags) if r.flags else dim("—")
    print(f"  {status_str}  {r.agent_name:<38} score={score_str}  {dim(r.mcp_server)}")
    if r.flags:
        print(f"         flags: {yellow(flags_str)}")

def print_decision(d, app):
    dec = d.decision
    if dec == Decision.APPROVE:
        dec_str = green(f"✅  APPROVED")
    elif dec == Decision.REFER:
        dec_str = yellow(f"🔄  REFERRED")
    else:
        dec_str = red(f"❌  REJECTED")

    print(f"\n{dec_str}  |  {bold('Score:')} {d.final_score:.1f}  |  {d.total_latency_ms}ms")
    if d.loan_terms:
        t = d.loan_terms
        print(f"  {bold('Amount:')} ₹{t.approved_amount:,.0f}  "
              f"{bold('Rate:')} {t.interest_rate_pa}% p.a.  "
              f"{bold('Tenure:')} {t.tenure_months}mo  "
              f"{bold('EMI:')} ₹{t.emi_amount:,.0f}/mo")
        print(f"  Processing Fee: ₹{t.processing_fee:,.0f}  |  "
              f"Total Repayable: ₹{t.total_repayable:,.0f}")
    if d.reason_codes:
        print(f"  {bold('Codes:')} {yellow(', '.join(d.reason_codes))}")
    if d.human_review_required:
        print(f"  {yellow('⚠  Human underwriter review required')}")

async def run_demo():
    print(f"\n{SEP}")
    print(f"  {bold(cyan('Real-Time Loan Approval — Multi-Agent AI Orchestration'))}")
    print(f"  MOCK_DATA={bold(str(settings.MOCK_DATA))}  Agents=5  MCP Servers=5  Timeout={settings.AGENT_TIMEOUT}s")
    print(SEP)

    orch = OrchestratorAgent()
    decisions = []

    for app in TEST_CASES:
        print(f"\n{SEP}")
        print(f"  {bold('Application:')} {cyan(app.application_id)}")
        print(f"  {bold('Customer:')}    {app.customer_name}")
        print(f"  {bold('Loan:')}        ₹{app.loan_amount:,.0f}  ×  {app.loan_tenure_months}mo  |  {app.loan_purpose.value}")
        print(f"  {bold('Income:')}      ₹{app.monthly_income:,.0f}/mo  ({app.employer_name})")
        print(f"{'─' * 70}")
        print("  Running agents in parallel...")
        print()

        d = await orch.process(app)
        decisions.append(d)

        for r in d.agent_results:
            print_agent_row(r)

        print_decision(d, app)

    # Summary
    print(f"\n\n{SEP}")
    print(f"  {bold('BATCH SUMMARY')}")
    print(f"{'─' * 70}")
    print(f"  {'Application ID':<16}  {'Customer':<22}  {'Decision':<10}  {'Score':>6}  {'Amount':>14}  {'Latency':>8}")
    print(f"  {'─'*16}  {'─'*22}  {'─'*10}  {'─'*6}  {'─'*14}  {'─'*8}")
    for d, app in zip(decisions, TEST_CASES):
        dec = (green if d.decision == Decision.APPROVE else
               yellow if d.decision == Decision.REFER else red)(f"{d.decision.value:<10}")
        amount = f"₹{d.loan_terms.approved_amount:,.0f}" if d.loan_terms else "—"
        print(f"  {d.application_id:<16}  {app.customer_name:<22}  {dec}  {d.final_score:6.1f}  {amount:>14}  {d.total_latency_ms:>6}ms")

    # JSON output for first approved
    approved = next((d for d in decisions if d.decision == Decision.APPROVE), None)
    if approved:
        print(f"\n\n{SEP}")
        print(f"  {bold('JSON OUTPUT')} — {approved.application_id}")
        print(f"{'─' * 70}")
        print(json.dumps(approved.summary(), indent=2))
    print()

if __name__ == "__main__":
    asyncio.run(run_demo())
