import streamlit as st

from eventtrader.settings import Settings

settings = Settings()

st.set_page_config(page_title="EventTrader", page_icon="📊")
st.title("EventTrader")
st.info("PAPER TRADING mode")
st.metric("Initial capital", f"${settings.starting_capital_usd:,.2f}")
st.write("Live trading: disabled")
st.caption(
    "Use Market Scanner for public data, Research Lab for bounded analysis, "
    "and Paper Trading for explicit simulated execution."
)
