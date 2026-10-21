"""Overview page."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from data import (
    get_monthly_late_rate,
    get_monthly_sales,
    get_overview_metrics,
    get_purchase_date_bounds,
)


@st.cache_data(ttl=300)
def load_dashboard_data(start_date: date, end_date: date):
    return (
        get_overview_metrics(start_date, end_date),
        get_monthly_sales(start_date, end_date),
        get_monthly_late_rate(start_date, end_date),
    )


def format_currency(value: object) -> str:
    return f"R$ {float(value):,.0f}"


def format_percent(value: object) -> str:
    return "—" if value is None else f"{float(value):.1%}"


st.title("Overview")
st.caption("Sales and delivery performance from the warehouse")

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
    metrics, monthly_sales, monthly_late_rate = load_dashboard_data(start_date, end_date)
except Exception as error:
    st.error(f"Could not load dashboard metrics: {error}")
    st.stop()

orders = int(metrics["orders"] or 0)
revenue = float(metrics["revenue"] or 0)
average_order_value = revenue / orders if orders else 0

revenue_col, orders_col, average_col, late_col = st.columns(4)
revenue_col.metric("Revenue", format_currency(revenue))
orders_col.metric("Orders", f"{orders:,}")
average_col.metric("Average order value", format_currency(average_order_value))
late_col.metric("Late-delivery rate", format_percent(metrics["late_rate"]))

sales_chart = make_subplots(specs=[[{"secondary_y": True}]])
sales_chart.add_trace(
    go.Bar(
        x=monthly_sales["month"],
        y=monthly_sales["revenue"],
        name="Revenue",
        marker_color="#2563eb",
    ),
    secondary_y=False,
)
sales_chart.add_trace(
    go.Scatter(
        x=monthly_sales["month"],
        y=monthly_sales["orders"],
        name="Orders",
        mode="lines+markers",
        line=dict(color="#f97316", width=3),
        marker=dict(color="#f97316", size=7),
    ),
    secondary_y=True,
)
sales_chart.update_layout(
    title="Monthly revenue and orders",
    legend=dict(orientation="h", y=1.1),
    plot_bgcolor="white",
    paper_bgcolor="rgba(0,0,0,0)",
    margin=dict(l=0, r=0, t=65, b=0),
)
sales_chart.update_yaxes(title_text="Revenue (R$)", secondary_y=False)
sales_chart.update_yaxes(title_text="Orders", secondary_y=True)
st.plotly_chart(sales_chart, use_container_width=True)

late_rate_chart = px.line(
    monthly_late_rate,
    x="month",
    y="late_rate",
    markers=True,
    color_discrete_sequence=["#e11d48"],
    title="Monthly late-delivery rate",
    labels={"month": "Month", "late_rate": "Late-delivery rate"},
)
late_rate_chart.update_yaxes(tickformat=".0%")
late_rate_chart.update_layout(
    margin=dict(l=0, r=0, t=45, b=0),
    plot_bgcolor="white",
    paper_bgcolor="rgba(0,0,0,0)",
)
st.plotly_chart(late_rate_chart, use_container_width=True)
