"""Display persisted public data through the API, without database credentials."""

import os

import httpx
import streamlit as st
from pydantic import TypeAdapter, ValidationError

from eventtrader.domain.markets import MarketRead

st.set_page_config(page_title="EventTrader Market Scanner", layout="wide")
st.title("Market Scanner")
st.info("READ-ONLY / PAPER MODE — Live trading: disabled")
st.caption("Manually synced snapshots, not streaming quotes. Missing values mean unknown.")
query = st.text_input("Search questions")
page = int(st.number_input("Page", min_value=1, value=1, step=1))
st.button("Refresh")
api_url = os.environ.get("EVENTTRADER_API_URL", "http://localhost:8000")
try:
    response = httpx.get(
        f"{api_url}/markets",
        params={"q": query, "limit": 50, "offset": (page - 1) * 50},
        timeout=10,
    )
    response.raise_for_status()
    markets = TypeAdapter(list[MarketRead]).validate_python(response.json())
except (httpx.HTTPError, ValidationError, ValueError):
    st.error("Market data unavailable. Start the API and apply database migrations.")
    st.stop()

if not markets:
    st.info("No synced markets match this search. Run the manual sync command.")
    st.stop()

rows = []
for market in markets:
    by_outcome = {snapshot.outcome_id: snapshot for snapshot in market.latest_snapshots}
    # A row per outcome prevents YES and NO prices from being silently mixed.
    for outcome in market.outcomes:
        snapshot = by_outcome.get(outcome.id)
        rows.append(
            {
                "Question": market.question,
                "Outcome": outcome.outcome_name,
                "Category": market.category,
                "Status": market.status,
                "Close time (UTC)": market.close_time.isoformat() if market.close_time else None,
                "Liquidity (market)": str(snapshot.liquidity)
                if snapshot and snapshot.liquidity is not None
                else None,
                "Volume (market)": str(snapshot.volume)
                if snapshot and snapshot.volume is not None
                else None,
                "Bid": str(snapshot.best_bid)
                if snapshot and snapshot.best_bid is not None
                else None,
                "Ask": str(snapshot.best_ask)
                if snapshot and snapshot.best_ask is not None
                else None,
                "Spread": str(snapshot.spread)
                if snapshot and snapshot.spread is not None
                else None,
                "Last snapshot (UTC)": snapshot.captured_at.isoformat() if snapshot else None,
            }
        )
    if not market.outcomes:
        rows.append(
            {"Question": market.question, "Status": market.status, "Category": market.category}
        )
st.dataframe(rows, hide_index=True)
st.caption("Liquidity and volume are market-wide and repeat per outcome; do not sum these rows.")
selected = st.selectbox(
    "Market detail", range(len(markets)), format_func=lambda index: markets[index].question
)
market = markets[selected]
st.subheader(market.question)
st.write("Resolution rules", market.resolution_rules or "Unknown")
st.write("Resolution source", market.resolution_source or "Unknown")
st.dataframe([outcome.model_dump(mode="json") for outcome in market.outcomes], hide_index=True)
st.write("Latest snapshot per outcome")
st.json([snapshot.model_dump(mode="json") for snapshot in market.latest_snapshots])
