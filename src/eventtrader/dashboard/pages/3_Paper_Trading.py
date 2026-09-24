"""Explicit paper execution UI. No provider order API exists."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import httpx
import streamlit as st

st.set_page_config(page_title="EventTrader Paper Trading", layout="wide")
st.title("Paper Trading")
st.error("SIMULATED EXECUTION — NO REAL MONEY")
st.caption("Orders consume stored public order-book depth. They never reach Polymarket.")

api_url = os.environ.get("EVENTTRADER_API_URL", "http://localhost:8000")
try:
    reports = httpx.get(f"{api_url}/research-runs", params={"limit": 100}, timeout=10).json()
    positions = httpx.get(f"{api_url}/paper/positions", timeout=10).json()
    orders = httpx.get(f"{api_url}/paper/orders", timeout=10).json()
except (httpx.HTTPError, ValueError):
    st.error("API unavailable.")
    st.stop()

approved = [
    item
    for item in reports
    if item["status"] == "APPROVED_FOR_PAPER" and item.get("result_payload")
]
mode = st.radio("Action", ["BUY approved proposal", "SELL held position"], horizontal=True)
selection = None
if mode.startswith("BUY"):
    if approved:
        selection = st.selectbox(
            "Approved proposal",
            approved,
            format_func=lambda item: f"{item['market_id']} · {item['graph_run_id']}",
        )
    else:
        st.info("No approved proposals are waiting for paper execution.")
else:
    open_positions = [item for item in positions if item["status"] == "OPEN"]
    if open_positions:
        selection = st.selectbox(
            "Open position",
            open_positions,
            format_func=lambda item: (
                f"{item['outcome_token_id']} · {item['quantity_shares']} shares"
            ),
        )
    else:
        st.info("No open position can be sold.")

if selection is not None:
    side = "BUY" if mode.startswith("BUY") else "SELL"
    report_id = selection["id"] if side == "BUY" else selection["trade_proposal_id"]
    default_limit = Decimal("0.50")
    if side == "BUY":
        proposal = selection["result_payload"]["proposal"]
        default_limit = Decimal(str(proposal["maximum_entry_price"]))
    with st.form("paper_order"):
        limit = Decimal(
            str(
                st.number_input(
                    "Limit price",
                    min_value=0.01,
                    max_value=0.99,
                    value=float(default_limit),
                    step=0.01,
                )
            )
        )
        if side == "BUY":
            spend = Decimal(
                str(
                    st.number_input(
                        "Requested paper spend (USD)",
                        min_value=0.01,
                        max_value=2.50,
                        value=2.50,
                        step=0.10,
                    )
                )
            )
            shares = spend / limit
        else:
            shares = Decimal(
                str(
                    st.number_input(
                        "Shares to sell",
                        min_value=0.01,
                        max_value=float(selection["quantity_shares"]),
                        value=float(selection["quantity_shares"]),
                        step=0.01,
                    )
                )
            )
            spend = shares * limit
        st.write("Expected shares", f"{shares:.6f}")
        st.write("Limit notional", f"USD {spend:.4f}")
        st.caption(
            "Fees, spread, and depth slippage are calculated from the stored snapshot at fill time."
        )
        submit = st.form_submit_button(f"Submit paper {side}")
    if submit:
        payload = {
            "trade_proposal_id": report_id,
            "side": side,
            "limit_price": str(limit),
            "requested_size_usd": str(spend) if side == "BUY" else None,
            "requested_shares": str(shares) if side == "SELL" else None,
            "idempotency_key": f"streamlit-{uuid4()}",
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }
        response = httpx.post(f"{api_url}/paper/orders", json=payload, timeout=30)
        if response.is_success:
            result = response.json()
            st.success(result["order"]["status"])
            st.json(result)
        else:
            st.error(response.text)

st.subheader("Paper order lifecycle")
if orders:
    st.dataframe(orders, hide_index=True)
else:
    st.info("No paper orders yet.")
