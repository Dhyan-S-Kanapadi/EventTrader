"""Inspect and run bounded research through the API. No order is ever created."""

import os

import httpx
import streamlit as st

st.set_page_config(page_title="EventTrader Research Lab", layout="wide")
st.title("Research Lab")
st.warning("READ-ONLY / PAPER MODE — research can only produce APPROVED_FOR_PAPER or REJECTED.")
st.caption("No wallet, signing key, order endpoint, or execution adapter exists.")

api_url = os.environ.get("EVENTTRADER_API_URL", "http://localhost:8000")
try:
    markets = httpx.get(f"{api_url}/markets", params={"limit": 100}, timeout=10).json()
except (httpx.HTTPError, ValueError):
    st.error("API unavailable.")
    st.stop()
if not markets:
    st.info("Sync markets before using the Research Lab.")
    st.stop()

selected = st.selectbox("Market", markets, format_func=lambda item: item["question"])
st.subheader(selected["question"])
st.write("Resolution rules", selected.get("resolution_rules") or "Unknown")
st.write("Resolution source", selected.get("resolution_source") or "Unknown")
snapshots = selected.get("latest_snapshots", [])
st.write("Latest prices")
st.dataframe(snapshots, hide_index=True)
st.write(
    "Configured risk limits",
    {
        "initial_capital_usd": "50",
        "max_single_position_usd": "2.50",
        "max_total_exposure_usd": "30",
        "min_cash_reserve_usd": "20",
    },
)

with st.form("manual_evidence"):
    source_url = st.text_input("Public source URL", placeholder="https://example.org/source")
    evidence_text = st.text_area("Development evidence text (stored as low trust)")
    submitted = st.form_submit_button("Add low-trust development evidence")
if submitted:
    payload = {
        "source_url": source_url,
        "extracted_text": evidence_text,
        "source_type": "manual_context",
        "trust_level": "low",
    }
    response = httpx.post(f"{api_url}/markets/{selected['id']}/evidence", json=payload, timeout=15)
    if response.is_success:
        st.success("Evidence saved with provenance and content hash.")
    else:
        st.error(response.text)

if st.button("Run Research", type="primary"):
    with st.spinner("Running bounded research graph..."):
        response = httpx.post(f"{api_url}/markets/{selected['id']}/research", timeout=120)
    if not response.is_success:
        st.error(response.text)
    else:
        result = response.json()
        st.subheader(result["status"])
        st.write("Reasons", result["reason_codes"] or ["All deterministic checks passed"])
        st.write("Graph stages")
        st.dataframe(result["stages"], hide_index=True)
        proposal = result.get("proposal")
        if proposal:
            cols = st.columns(4)
            cols[0].metric("Estimated probability", proposal["proposal"]["estimated_probability"])
            cols[1].metric("Research cost", f"$ {proposal['total_research_cost_usd']}")
            cols[2].metric("Gross expected profit", f"$ {proposal['gross_expected_profit_usd']}")
            cols[3].metric("Net expected profit", f"$ {proposal['net_expected_profit_usd']}")
            st.write("Counterarguments", proposal["proposal"]["counterarguments"])
            st.write("Evidence IDs", proposal["proposal"]["evidence_ids"])
        st.info("This result did not create or submit an order.")
