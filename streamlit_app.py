"""
streamlit_app.py
================
Streamlit UI for the Loan Approval AI system.

Run:
  # Terminal 1 — MCP servers
  MOCK_DATA=true python3 mcp_servers/run_servers.py

  # Terminal 2 — API server
  MOCK_DATA=true python3 app_server.py

  # Terminal 3 — Streamlit
  streamlit run streamlit_app.py
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

import requests
import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("MOCK_DATA", "true")

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LoanAI — Multi-Agent Decision Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Constants ─────────────────────────────────────────────────────────────────
API_URL = os.environ.get("LOAN_API_URL", "http://localhost:8000")

TEST_PROFILES = {
    "✅  Priya Sharma (Approve)": {
        "customer_name": "Priya Sharma",
        "pan_number": "ABCPS1234P",
        "aadhaar_number": "9876-5432-1098",
        "date_of_birth": "1988-04-15",
        "mobile": "9876543210",
        "email": "priya.sharma@gmail.com",
        "loan_amount": 500000.0,
        "loan_tenure_months": 36,
        "loan_purpose": "home_renovation",
        "monthly_income": 85000.0,
        "employer_name": "Tata Consultancy Services",
        "employment_type": "salaried",
        "years_of_employment": 6.5,
        "residential_address": "42 MG Road, Bengaluru",
        "city": "Bengaluru",
        "pincode": "560001",
    },
    "🔄  Zubair Ali Khan (Refer)": {
        "customer_name": "Zubair Ali Khan",
        "pan_number": "ZZXZA9999Z",
        "aadhaar_number": "1234-5678-9012",
        "date_of_birth": "1975-11-30",
        "mobile": "9123456780",
        "email": "zubair.khan@company.com",
        "loan_amount": 1500000.0,
        "loan_tenure_months": 60,
        "loan_purpose": "business",
        "monthly_income": 180000.0,
        "employer_name": "Self-Employed",
        "employment_type": "self_employed",
        "years_of_employment": 10.0,
        "residential_address": "15 Juhu Tara Road, Mumbai",
        "city": "Mumbai",
        "pincode": "400049",
    },
    "❌  Fraudster (Reject)": {
        "customer_name": "Fraudster One",
        "pan_number": "FAKEX0000X",
        "aadhaar_number": "0000-0000-0001",
        "date_of_birth": "1990-01-01",
        "mobile": "0000000001",
        "email": "hacker@fraud.com",
        "loan_amount": 2000000.0,
        "loan_tenure_months": 24,
        "loan_purpose": "personal",
        "monthly_income": 10000.0,
        "employer_name": "Unknown Corp",
        "employment_type": "salaried",
        "years_of_employment": 0.0,
        "residential_address": "Unknown",
        "city": "Unknown",
        "pincode": "000000",
    },
    "🏠  Rahul Mehta (Home Loan)": {
        "customer_name": "Rahul Mehta",
        "pan_number": "ABCRM5678M",
        "aadhaar_number": "5555-6666-7777",
        "date_of_birth": "1982-07-20",
        "mobile": "8765432190",
        "email": "rahul.mehta@infosys.com",
        "loan_amount": 3000000.0,
        "loan_tenure_months": 120,
        "loan_purpose": "home_purchase",
        "monthly_income": 150000.0,
        "employer_name": "Infosys Limited",
        "employment_type": "salaried",
        "years_of_employment": 12.0,
        "residential_address": "78 Sector 15, Noida",
        "city": "Noida",
        "pincode": "201301",
    },
}

LOAN_PURPOSES = [
    "personal", "home_purchase", "home_renovation",
    "vehicle", "education", "medical",
    "business", "debt_consolidation",
]

EMPLOYMENT_TYPES = ["salaried", "self_employed", "business"]

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Font imports */
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

/* Global */
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

/* Hide streamlit chrome */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* Main background */
.stApp { background-color: #F7F5F0; }
section[data-testid="stSidebar"] { background: #0F2645; }
section[data-testid="stSidebar"] * { color: rgba(255,255,255,0.85) !important; }
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label { color: rgba(255,255,255,0.55) !important; font-size: 11px !important; letter-spacing: 0.06em !important; text-transform: uppercase !important; }

/* Decision cards */
.decision-card {
    border-radius: 16px; padding: 28px 32px;
    margin-bottom: 16px;
}
.decision-approve { background: #ECFDF5; border: 1px solid rgba(5,122,85,0.2); }
.decision-refer   { background: #FFFBEB; border: 1px solid rgba(146,64,14,0.2); }
.decision-reject  { background: #FEF2F2; border: 1px solid rgba(155,28,28,0.2); }

.verdict-text {
    font-family: 'DM Serif Display', serif;
    font-size: 42px; line-height: 1;
    margin-bottom: 8px;
}
.verdict-approve { color: #057A55; }
.verdict-refer   { color: #92400E; }
.verdict-reject  { color: #9B1C1C; }

/* Agent rows */
.agent-row {
    display: flex; align-items: center;
    padding: 10px 0;
    border-bottom: 1px solid rgba(0,0,0,0.07);
    gap: 12px;
}
.agent-row:last-child { border-bottom: none; }

/* Metric cards */
.metric-card {
    background: white; border-radius: 12px;
    padding: 16px 20px; border: 1px solid rgba(0,0,0,0.08);
    text-align: center;
}
.metric-label { font-size: 11px; color: #6B6760; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 4px; }
.metric-value { font-family: 'DM Serif Display', serif; font-size: 28px; color: #0F2645; }

/* Flag badges */
.flag-badge {
    display: inline-block; font-size: 10px;
    font-family: 'JetBrains Mono', monospace;
    padding: 2px 8px; border-radius: 4px;
    background: #FEE2E2; color: #9B1C1C;
    margin: 2px;
}

/* Score bar */
.score-bar-container {
    background: #F7F5F0; border-radius: 999px;
    height: 6px; overflow: hidden;
}
.score-bar { height: 100%; border-radius: 999px; }
.score-bar-pass   { background: #057A55; }
.score-bar-fail   { background: #9B1C1C; }
.score-bar-error  { background: #9E9B96; }

/* Section headers */
.section-header {
    font-size: 11px; font-weight: 600; color: #9E9B96;
    letter-spacing: 0.1em; text-transform: uppercase;
    margin-bottom: 12px; margin-top: 4px;
}

/* History rows */
.history-row {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 12px; border-radius: 8px;
    background: white; border: 1px solid rgba(0,0,0,0.07);
    margin-bottom: 6px;
}

/* Term cell */
.term-cell {
    background: white; border-radius: 10px;
    padding: 14px 18px; border: 1px solid rgba(0,0,0,0.08);
}
.term-label { font-size: 10px; color: #6B6760; text-transform: uppercase; letter-spacing: 0.06em; }
.term-value { font-family: 'DM Serif Display', serif; font-size: 20px; color: #0F2645; margin-top: 2px; }
.term-sub   { font-size: 11px; color: #9E9B96; }

/* Status dot */
.dot-pass  { color: #057A55; }
.dot-fail  { color: #9B1C1C; }
.dot-error { color: #9E9B96; }
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
if "history" not in st.session_state:
    st.session_state.history = []
if "last_decision" not in st.session_state:
    st.session_state.last_decision = None
if "form_data" not in st.session_state:
    st.session_state.form_data = {}


# ── Helpers ───────────────────────────────────────────────────────────────────
def check_api() -> bool:
    try:
        r = requests.get(f"{API_URL}/api/v1/health", timeout=2)
        return r.ok
    except Exception:
        return False


def fmt_inr(amount: float) -> str:
    return f"₹{amount:,.0f}"


def submit_application(payload: dict) -> dict:
    r = requests.post(
        f"{API_URL}/api/v1/loans/apply",
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def verdict_color(v: str) -> str:
    return {"approve": "#057A55", "refer": "#92400E", "reject": "#9B1C1C"}.get(v, "#333")


def verdict_emoji(v: str) -> str:
    return {"approve": "✅", "refer": "🔄", "reject": "❌"}.get(v, "⚡")


def status_dot(s: str) -> str:
    dots = {"pass": "🟢", "fail": "🔴", "error": "⚪"}
    return dots.get(s, "⚪")


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚡ LoanAI")
    st.markdown("<p style='font-size:12px;color:rgba(255,255,255,0.4);margin-top:-8px'>Multi-Agent Decision Engine</p>", unsafe_allow_html=True)
    st.divider()

    # API status
    api_ok = check_api()
    status_color = "#34D399" if api_ok else "#F87171"
    status_text  = "API Online" if api_ok else "API Offline"
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:16px'>"
        f"<span style='width:8px;height:8px;border-radius:50%;background:{status_color};display:inline-block'></span>"
        f"<span style='font-size:12px;font-family:monospace;color:{status_color}'>{status_text}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not api_ok:
        st.warning("Start the API server:\n```\nMOCK_DATA=true python3 app_server.py\n```")

    st.markdown("<div class='section-header' style='color:rgba(255,255,255,0.4)'>Test Profiles</div>", unsafe_allow_html=True)
    selected_profile = st.selectbox(
        "Load a test profile",
        ["— select —"] + list(TEST_PROFILES.keys()),
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("<div class='section-header' style='color:rgba(255,255,255,0.4)'>Architecture</div>", unsafe_allow_html=True)

    agents_info = [
        ("📄 Document",  "20%", "NSDL / UIDAI"),
        ("💳 Credit",    "35%", "CIBIL / Experian"),
        ("🏦 Income",    "25%", "Account Aggregator"),
        ("🛡 Risk",      "15%", "Fraud ML"),
        ("⚖️ Compliance", "5%",  "OFAC / AML"),
    ]
    for name, wt, src in agents_info:
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;padding:4px 0;"
            f"border-bottom:1px solid rgba(255,255,255,0.06);font-size:12px'>"
            f"<span>{name}</span><span style='color:rgba(255,255,255,0.4);font-family:monospace'>{wt}</span></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.session_state.history:
        st.markdown("<div class='section-header' style='color:rgba(255,255,255,0.4)'>History</div>", unsafe_allow_html=True)
        for i, h in enumerate(st.session_state.history[-5:]):
            v = h["decision"].lower()
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"<div style='font-size:12px'>{verdict_emoji(v)} {h['name']}</div>",
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    f"<div style='font-size:11px;font-family:monospace;color:rgba(255,255,255,0.4);text-align:right'>{h['score']:.0f}</div>",
                    unsafe_allow_html=True,
                )


# ── Main area ─────────────────────────────────────────────────────────────────
st.markdown(
    "<h1 style='font-family:DM Serif Display,serif;font-size:32px;color:#0F2645;margin-bottom:4px'>Loan Application</h1>"
    "<p style='color:#6B6760;font-size:14px;margin-bottom:24px'>Real-time AI scoring across 5 specialist agents</p>",
    unsafe_allow_html=True,
)

# Fill from profile
profile_data = {}
if selected_profile != "— select —":
    profile_data = TEST_PROFILES[selected_profile]

def pv(key, default=""):
    return profile_data.get(key, st.session_state.form_data.get(key, default))


# ── Application form ───────────────────────────────────────────────────────────
with st.form("loan_form", clear_on_submit=False):

    # Personal details
    st.markdown("<div class='section-header'>Personal Details</div>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        customer_name   = st.text_input("Full Name *", value=pv("customer_name"))
        pan_number      = st.text_input("PAN Number *", value=pv("pan_number"), max_chars=10)
        mobile          = st.text_input("Mobile *", value=pv("mobile"))
    with c2:
        date_of_birth   = st.text_input("Date of Birth (YYYY-MM-DD) *", value=pv("date_of_birth"))
        aadhaar_number  = st.text_input("Aadhaar Number *", value=pv("aadhaar_number"))
        email           = st.text_input("Email *", value=pv("email"))

    st.divider()

    # Loan details
    st.markdown("<div class='section-header'>Loan Details</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        loan_amount     = st.number_input("Loan Amount (₹) *", min_value=10000.0, value=float(pv("loan_amount", 500000)), step=10000.0)
    with c2:
        loan_tenure     = st.number_input("Tenure (months) *", min_value=6, max_value=360, value=int(pv("loan_tenure_months", 36)))
    with c3:
        loan_purpose    = st.selectbox("Loan Purpose", LOAN_PURPOSES,
                                       index=LOAN_PURPOSES.index(pv("loan_purpose", "personal")) if pv("loan_purpose", "personal") in LOAN_PURPOSES else 0)

    st.divider()

    # Employment
    st.markdown("<div class='section-header'>Employment</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        monthly_income  = st.number_input("Monthly Income (₹) *", min_value=1000.0, value=float(pv("monthly_income", 50000)), step=1000.0)
    with c2:
        employer_name   = st.text_input("Employer Name *", value=pv("employer_name"))
    with c3:
        employment_type = st.selectbox("Employment Type", EMPLOYMENT_TYPES,
                                       index=EMPLOYMENT_TYPES.index(pv("employment_type", "salaried")) if pv("employment_type", "salaried") in EMPLOYMENT_TYPES else 0)

    c1, c2 = st.columns(2)
    with c1:
        years_employed  = st.number_input("Years Employed", min_value=0.0, value=float(pv("years_of_employment", 1.0)), step=0.5)

    st.divider()

    # Address
    st.markdown("<div class='section-header'>Address</div>", unsafe_allow_html=True)
    residential_address = st.text_input("Residential Address *", value=pv("residential_address"))
    c1, c2, c3 = st.columns(3)
    with c1:
        city    = st.text_input("City", value=pv("city"))
    with c2:
        pincode = st.text_input("Pincode", value=pv("pincode"), max_chars=6)
    with c3:
        ip_address = st.text_input("IP Address", value=pv("ip_address", "0.0.0.0"))

    st.markdown("<br>", unsafe_allow_html=True)
    submitted = st.form_submit_button(
        "⚡  Submit Application",
        use_container_width=True,
        type="primary",
    )


# ── Process submission ─────────────────────────────────────────────────────────
if submitted:
    errors = []
    if not customer_name:   errors.append("Full name is required")
    if not pan_number:      errors.append("PAN number is required")
    if not aadhaar_number:  errors.append("Aadhaar number is required")
    if not date_of_birth:   errors.append("Date of birth is required")
    if not mobile:          errors.append("Mobile is required")
    if not email:           errors.append("Email is required")
    if not employer_name:   errors.append("Employer name is required")
    if not residential_address: errors.append("Residential address is required")

    if errors:
        for e in errors:
            st.error(e)
    elif not api_ok:
        st.error("API is offline. Start `app_server.py` first.")
    else:
        payload = {
            "customer_name":       customer_name,
            "pan_number":          pan_number.upper(),
            "aadhaar_number":      aadhaar_number,
            "date_of_birth":       date_of_birth,
            "mobile":              mobile,
            "email":               email,
            "loan_amount":         loan_amount,
            "loan_tenure_months":  int(loan_tenure),
            "loan_purpose":        loan_purpose,
            "monthly_income":      monthly_income,
            "employer_name":       employer_name,
            "employment_type":     employment_type,
            "years_of_employment": years_employed,
            "residential_address": residential_address,
            "city":                city,
            "pincode":             pincode,
            "ip_address":          ip_address or "0.0.0.0",
        }

        with st.spinner("Running 5 AI agents in parallel..."):
            try:
                decision = submit_application(payload)
                st.session_state.last_decision = decision
                st.session_state.history.insert(0, {
                    "name":       customer_name,
                    "decision":   decision["decision"],
                    "score":      decision["final_score"],
                    "app_id":     decision["application_id"],
                    "time":       datetime.now().strftime("%H:%M:%S"),
                    "full":       decision,
                })
                if len(st.session_state.history) > 20:
                    st.session_state.history.pop()
            except Exception as e:
                st.error(f"Error: {e}")


# ── Display last decision ──────────────────────────────────────────────────────
if st.session_state.last_decision:
    d = st.session_state.last_decision
    verdict = d["decision"].lower()

    st.markdown("---")
    st.markdown(
        "<h2 style='font-family:DM Serif Display,serif;font-size:24px;color:#0F2645;margin-bottom:16px'>Decision Result</h2>",
        unsafe_allow_html=True,
    )

    # ── Verdict hero ──
    verdict_labels = {"approve": "✅ Approved", "refer": "🔄 Referred to Underwriter", "reject": "❌ Rejected"}
    card_class     = f"decision-{verdict}"
    verdict_class  = f"verdict-{verdict}"

    st.markdown(
        f"<div class='decision-card {card_class}'>"
        f"  <div class='verdict-text {verdict_class}'>{verdict_labels.get(verdict, verdict.upper())}</div>"
        f"  <div style='font-size:13px;color:#6B6760;margin-top:4px'>"
        f"    Application {d['application_id']} · "
        f"    Score {d['final_score']:.1f}/100 · "
        f"    {d['total_latency_ms']}ms"
        f"  </div>"
        f"  {('<div style=\"margin-top:10px;font-size:13px;color:#92400E;font-weight:500\">⚠ Human underwriter review required</div>' if d.get('human_review_required') else '')}"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── Loan terms ──
    if d.get("loan_terms"):
        t = d["loan_terms"]
        st.markdown("<div class='section-header'>Loan Terms</div>", unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        terms_data = [
            (c1, "Approved Amount",  fmt_inr(t["approved_amount"]),  ""),
            (c2, "Interest Rate",    f"{t['interest_rate_pa']}%",    "per annum"),
            (c3, "Monthly EMI",      fmt_inr(t["emi_amount"]),       f"{t['tenure_months']} months"),
            (c4, "Processing Fee",   fmt_inr(t["processing_fee"]),   ""),
            (c5, "Total Repayable",  fmt_inr(t["total_repayable"]),  ""),
        ]
        for col, label, value, sub in terms_data:
            with col:
                st.markdown(
                    f"<div class='term-cell'>"
                    f"  <div class='term-label'>{label}</div>"
                    f"  <div class='term-value'>{value}</div>"
                    f"  {'<div class=\"term-sub\">'+sub+'</div>' if sub else ''}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── Reason codes ──
    if d.get("reason_codes"):
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<div class='section-header'>Reason Codes</div>", unsafe_allow_html=True)
        badges = " ".join(f"<span class='flag-badge'>{r}</span>" for r in d["reason_codes"])
        st.markdown(badges, unsafe_allow_html=True)

    # ── Agent breakdown ──
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<div class='section-header'>Agent Breakdown</div>", unsafe_allow_html=True)

    for agent in d.get("agent_breakdown", []):
        name   = agent["agent"]
        score  = agent["score"]
        weight = agent["weight"]
        status = agent["status"]
        flags  = agent.get("flags", [])
        ms     = agent.get("ms", 0)

        dot    = status_dot(status)
        bar_class = f"score-bar-{status}"

        col_dot, col_name, col_bar, col_score, col_weight, col_ms = st.columns([0.5, 3, 3, 1, 1, 1])

        with col_dot:
            st.markdown(f"<div style='padding-top:8px;font-size:14px'>{dot}</div>", unsafe_allow_html=True)

        with col_name:
            flags_html = " ".join(f"<span class='flag-badge'>{f}</span>" for f in flags)
            st.markdown(
                f"<div style='padding-top:6px'>"
                f"  <div style='font-size:13px;font-weight:500;color:#1A1814'>{name}</div>"
                f"  {'<div style=\"margin-top:3px\">'+flags_html+'</div>' if flags else ''}"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_bar:
            st.markdown(
                f"<div style='padding-top:14px'>"
                f"  <div class='score-bar-container'>"
                f"    <div class='score-bar {bar_class}' style='width:{score}%'></div>"
                f"  </div>"
                f"</div>",
                unsafe_allow_html=True,
            )

        with col_score:
            score_color = verdict_color(status if status in ("approve","refer","reject") else ("approve" if status == "pass" else ("reject" if status == "fail" else "refer")))
            pass_fail_color = "#057A55" if status == "pass" else "#9B1C1C" if status == "fail" else "#9E9B96"
            st.markdown(
                f"<div style='padding-top:6px;font-family:JetBrains Mono,monospace;font-size:14px;"
                f"font-weight:500;color:{pass_fail_color};text-align:right'>{score:.0f}</div>",
                unsafe_allow_html=True,
            )

        with col_weight:
            st.markdown(
                f"<div style='padding-top:6px;font-family:JetBrains Mono,monospace;"
                f"font-size:11px;color:#9E9B96;text-align:right'>{int(weight*100)}%</div>",
                unsafe_allow_html=True,
            )

        with col_ms:
            st.markdown(
                f"<div style='padding-top:6px;font-family:JetBrains Mono,monospace;"
                f"font-size:11px;color:#9E9B96;text-align:right'>{ms}ms</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<hr style='margin:4px 0;border-color:rgba(0,0,0,0.05)'>", unsafe_allow_html=True)

    # ── Raw JSON expander ──
    with st.expander("View raw JSON response"):
        st.json(d)
