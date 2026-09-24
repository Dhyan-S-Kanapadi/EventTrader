"""Paper portfolio visibility with cost and exposure charts."""

import os

import httpx
import plotly.express as px  # type: ignore[import-not-found]
import streamlit as st

st.set_page_config(page_title="EventTrader Portfolio", layout="wide")
st.title("Paper Portfolio")
st.error("SIMULATED EXECUTION — NO REAL MONEY")

api_url = os.environ.get("EVENTTRADER_API_URL", "http://localhost:8000")
if st.button("Mark positions to market"):
    httpx.post(f"{api_url}/paper/portfolio/mark", timeout=30)
try:
    portfolio = httpx.get(f"{api_url}/paper/portfolio", timeout=10).json()
except (httpx.HTTPError, ValueError):
    st.error("Portfolio API unavailable.")
    st.stop()

columns = st.columns(6)
metrics = [
    ("Starting capital", "starting_capital_usd"),
    ("Available cash", "available_cash_usd"),
    ("Reserved cash", "reserved_cash_usd"),
    ("Open exposure", "open_exposure_usd"),
    ("Realized P&L", "realized_pnl_usd"),
    ("Unrealized P&L", "unrealized_pnl_usd"),
]
for column, (label, key) in zip(columns, metrics, strict=True):
    column.metric(label, f"USD {portfolio[key]}")

st.metric("Total net P&L after recorded costs", f"USD {portfolio['total_net_pnl_usd']}")
positions = portfolio["positions"]
st.subheader("Positions")
st.dataframe(positions, hide_index=True)

events = portfolio["events"]
if events:
    equity = [
        {
            "time": item["created_at"],
            "paper_cash_usd": item["balance_after_usd"],
        }
        for item in events
    ]
    st.plotly_chart(
        px.line(equity, x="time", y="paper_cash_usd", title="Paper cash curve"),
        width="stretch",
    )
if positions:
    exposure = [
        {
            "token": item["outcome_token_id"],
            "cost_basis_usd": item["cost_basis_usd"],
        }
        for item in positions
        if item["status"] == "OPEN"
    ]
    if exposure:
        st.plotly_chart(
            px.bar(
                exposure,
                x="token",
                y="cost_basis_usd",
                title="Open exposure by outcome",
            ),
            width="stretch",
        )

costs = {
    "Fees": portfolio["total_fees_usd"],
    "Spread": portfolio["total_spread_cost_usd"],
    "Slippage": portfolio["total_slippage_usd"],
    "Research": portfolio["total_research_cost_usd"],
}
st.plotly_chart(
    px.bar(
        x=list(costs),
        y=list(costs.values()),
        labels={"x": "Cost", "y": "USD"},
        title="Recorded cost breakdown",
    ),
    width="stretch",
)
st.caption("Position trade_proposal_id links each position to its research thesis.")
