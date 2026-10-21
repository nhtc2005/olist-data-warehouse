"""Sales analysis page."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import plotly.express as px
import streamlit as st


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from data import (
    get_purchase_date_bounds,
    get_sales_by_category,
    get_sales_by_customer_state,
)


@st.cache_data(ttl=300)
def load_sales_breakdowns(start_date: date, end_date: date):
    return (
        get_sales_by_category(start_date, end_date),
        get_sales_by_customer_state(start_date, end_date),
    )


def format_currency(value: object) -> str:
    return f"R$ {float(value):,.0f}"


def sales_table(frame, group_column: str):
    summary = frame.copy()
    summary["average_order_value"] = summary["revenue"] / summary["orders"]
    summary["revenue"] = summary["revenue"].map(format_currency)
    summary["average_order_value"] = summary["average_order_value"].map(format_currency)
    return st.dataframe(
        summary.rename(
            columns={
                group_column: "Group",
                "revenue": "Revenue",
                "orders": "Orders",
                "average_order_value": "Average order value",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )


st.title("Sales analysis")
st.caption("Top product categories and customer states by revenue")

try:
    first_purchase, last_purchase = get_purchase_date_bounds()
except Exception as error:
    st.error(f"Could not read warehouse data: {error}")
    st.stop()

with st.sidebar:
    st.header("Filters")
    selected_dates = st.date_input(
        "Purchase period",
        value=(first_purchase, last_purchase),
        min_value=first_purchase,
        max_value=last_purchase,
    )

if not isinstance(selected_dates, tuple) or len(selected_dates) != 2:
    st.info("Select a start and end date to view the dashboard.")
    st.stop()

start_date, end_date = selected_dates
if start_date > end_date:
    st.error("The start date must not be after the end date.")
    st.stop()

try:
    category_sales, state_sales = load_sales_breakdowns(start_date, end_date)
except Exception as error:
    st.error(f"Could not load sales analysis: {error}")
    st.stop()

category_col, state_col = st.columns(2)
with category_col:
    category_chart = px.bar(
        category_sales.sort_values("revenue"),
        x="revenue",
        y="category",
        orientation="h",
        title="Top categories by revenue",
        labels={"category": "Category", "revenue": "Revenue (R$)"},
        color_discrete_sequence=["#2563eb"],
    )
    category_chart.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=45, b=0),
    )
    st.plotly_chart(category_chart, use_container_width=True)

with state_col:
    state_chart = px.bar(
        state_sales.sort_values("revenue"),
        x="revenue",
        y="customer_state",
        orientation="h",
        title="Top customer states by revenue",
        labels={"customer_state": "State", "revenue": "Revenue (R$)"},
        color_discrete_sequence=["#7c3aed"],
    )
    state_chart.update_layout(
        plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=45, b=0),
    )
    st.plotly_chart(state_chart, use_container_width=True)

category_table_col, state_table_col = st.columns(2)
with category_table_col:
    st.subheader("Category summary")
    sales_table(category_sales, "category")

with state_table_col:
    st.subheader("State summary")
    sales_table(state_sales, "customer_state")
