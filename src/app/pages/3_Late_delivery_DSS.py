"""Late-delivery decision-support page."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from data import (
    get_model_metadata,
    get_monthly_high_risk,
    get_risk_customer_states,
    get_risk_orders,
    get_risk_summary,
)


@st.cache_data(ttl=300)
def load_risk_data(population: str, customer_state: str, only_high_risk: bool):
    return (
        get_risk_summary(population, customer_state),
        get_monthly_high_risk(population, customer_state),
        get_risk_orders(population, customer_state, only_high_risk),
    )


def format_percent(value: object) -> str:
    return f"{float(value):.1%}"


def format_currency(value: object) -> str:
    return f"R$ {float(value):,.0f}"


def present_risk_orders(orders: pd.DataFrame) -> pd.DataFrame:
    display = orders.copy()
    display["purchase_date"] = display["purchase_date"].astype(str)
    display["promised_lead_time_days"] = display["promised_lead_time_days"].map(
        lambda value: "—" if pd.isna(value) else f"{float(value):.1f}"
    )
    display["total_order_value"] = display["total_order_value"].map(format_currency)
    display["has_out_of_state_seller"] = display["has_out_of_state_seller"].map(
        {True: "Yes", False: "No"}
    ).fillna("—")
    display["risk_probability"] = display["risk_probability"].map(format_percent)
    return display.rename(
        columns={
            "order_id": "Order ID",
            "purchase_date": "Purchase date",
            "customer_state": "Customer state",
            "promised_lead_time_days": "Promised lead time (days)",
            "item_count": "Items",
            "total_order_value": "Order value",
            "has_out_of_state_seller": "Out-of-state seller",
            "risk_probability": "Late-delivery probability",
            "risk_band": "Risk band",
        }
    )


st.title("Late-delivery DSS")
st.caption("Prioritise orders with a higher predicted risk of late delivery")

try:
    metadata = get_model_metadata()
    customer_states = get_risk_customer_states()
except Exception as error:
    st.error(f"Could not read model output: {error}")
    st.stop()

population_labels = {
    "All scored orders": "all",
    "Test": "test",
    "Validation": "validation",
}
with st.sidebar:
    st.header("Risk filters")
    population_label = st.selectbox("Scored population", population_labels)
    selected_state = st.selectbox("Customer state", ["All", *customer_states])
    only_high_risk = st.checkbox("High-risk orders only", value=True)

population = population_labels[population_label]
customer_state = "all" if selected_state == "All" else selected_state

try:
    summary, monthly_high_risk, risk_orders = load_risk_data(
        population, customer_state, only_high_risk
    )
except Exception as error:
    st.error(f"Could not load risk scores: {error}")
    st.stop()

test_metrics = metadata["test_metrics"]
threshold = metadata["alert_threshold"]
pr_auc_col, threshold_col, scored_col, high_risk_col = st.columns(4)
pr_auc_col.metric("Test PR-AUC", f"{float(test_metrics['pr_auc']):.3f}")
threshold_col.metric("Alert threshold", format_percent(threshold))
scored_col.metric("Scored orders", f"{int(summary['scored_orders'] or 0):,}")
high_risk_col.metric("High-risk orders", f"{int(summary['high_risk_orders'] or 0):,}")

st.caption(
    "Logistic Regression flags an order as high risk when its predicted probability "
    "meets or exceeds the alert threshold."
)

high_risk_chart = px.bar(
    monthly_high_risk,
    x="month",
    y="high_risk_orders",
    title="High-risk orders by month",
    labels={"month": "Month", "high_risk_orders": "High-risk orders"},
    color_discrete_sequence=["#e11d48"],
)
high_risk_chart.update_layout(
    plot_bgcolor="white",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=45, b=0),
)
st.plotly_chart(high_risk_chart, use_container_width=True)

st.subheader("Orders to monitor")
st.caption("Results are ordered by predicted late-delivery probability; up to 500 rows are shown.")
st.dataframe(present_risk_orders(risk_orders), hide_index=True, use_container_width=True, height=480)
