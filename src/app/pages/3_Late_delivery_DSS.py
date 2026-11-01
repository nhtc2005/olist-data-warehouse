"""Capacity-based order prioritisation evaluated on historical test orders."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import plotly.graph_objects as go
import streamlit as st

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
from data import get_model_metadata, get_test_review_data


def percent(value):
    return "—" if value is None else f"{value:.1%}"


st.title("Delivery risk simulation")
st.caption("Choose review capacity and prioritise orders by predicted late-delivery risk.")
try:
    metadata = get_model_metadata()
    # Never reuse cached scores after an upstream refresh.
    orders = get_test_review_data(metadata)
except Exception as error:
    st.error(f"Could not load consistent risk scores: {error}")
    st.stop()

period = metadata["splits"]["test"]
st.caption(f"Historical test orders: {period['start_date']} to {period['end_date']}. "
           "The model uses information available before delivery. This is not a live shipment feed.")
with st.sidebar:
    st.header("Review planning")
    state = st.selectbox("Customer state", ["All", *sorted(orders.customer_state.unique())])
    capacity = st.slider("Orders the team can review (%)", 0, 100, 10, 1, format="%d%%",
                         help="Capacity is rounded down to whole orders within the selected group.")
cohort = orders if state == "All" else orders.loc[orders.customer_state.eq(state)]
if cohort.empty:
    st.info("No test orders match these filters.")
    st.stop()
count = len(cohort)
budget = count * capacity // 100
selected = cohort.iloc[:budget].copy()
total_late = int(cohort.is_late.sum())
captured = int(selected.is_late.sum())
precision = captured / budget if budget else None
coverage = captured / total_late if total_late else None
late_rate = total_late / count
random_expected = budget * late_rate
lift = precision / late_rate if precision is not None and late_rate else None
f1 = 2 * captured / (budget + total_late) if budget + total_late else None
st.caption(f"{count:,} orders in the selected group. Review capacity applies to this entire group.")
if count < 100:
    st.warning("This group has fewer than 100 orders. Historical results may vary substantially with a few orders.")
if total_late == 0:
    st.info("There were no late deliveries in this group. Late-order coverage and lift are undefined.")

st.subheader("Orders to monitor")
st.write("Review these orders first. Check fulfilment progress with the seller or carrier, verify the delivery commitment, and consider contacting the customer after verification.")
st.caption(f"Showing the first {min(budget, 500):,} of {budget:,} prioritised orders. Ranking uses predicted risk, with order ID as the tie-breaker.")
display = selected.drop(columns="is_late").copy()
display.insert(0, "priority", np.arange(1, budget + 1))
for column in ("promised_lead_time_days", "total_order_value", "risk_probability"):
    display[column] = display[column].astype(float)
display["risk_probability"] *= 100
configs = {
    "priority": st.column_config.NumberColumn("Priority", format="%d"),
    "order_id": st.column_config.TextColumn("Order ID"),
    "purchase_date": st.column_config.DateColumn("Purchase date"),
    "promised_delivery_date": st.column_config.DateColumn("Promised delivery date"),
    "customer_state": st.column_config.TextColumn("Customer state"),
    "promised_lead_time_days": st.column_config.NumberColumn("Promised lead time (days)", format="%.1f"),
    "item_count": st.column_config.NumberColumn("Items", format="%d"),
    "total_order_value": st.column_config.NumberColumn("Order value (incl. freight)", format="R$ %.2f"),
    "risk_probability": st.column_config.NumberColumn("Predicted late-delivery risk (%)", format="%.2f%%"),
}
if budget:
    st.dataframe(display.head(500), column_config=configs, hide_index=True, width="stretch", height=400)
else:
    st.info("Increase review capacity to include orders in the monitoring list.")
st.download_button("Download monitoring list", display.to_csv(index=False).encode("utf-8"),
                   file_name="orders_to_monitor.csv", mime="text/csv", disabled=budget == 0,
                   help="Exports the entire priority list. Risk is expressed as a percentage.")

st.subheader("Historical evaluation")
st.caption("Known delivery outcomes are used only to evaluate the selected list, not to rank orders. Captured late orders do not mean delays prevented.")
columns = st.columns(4)
columns[0].metric("Orders to review", f"{budget:,}")
columns[1].metric("Historical late orders captured", f"{captured:,}")
columns[2].metric("Late-order coverage", percent(coverage), help="Share of all historical late orders included in the monitoring list.")
columns[3].metric("Reviewed orders delivered on time", f"{budget - captured:,}")
st.write(f"Reviewing {budget:,} prioritised orders includes {captured:,} of {total_late:,} historical late orders; {total_late - captured:,} late orders remain outside the list.")
st.write(f"Randomly reviewing the same number of orders would capture {random_expected:,.1f} late orders on average. "
         + (f"Risk prioritisation captures {lift:.2f}× as many." if lift is not None else "A comparison ratio is unavailable for this selection."))
if total_late:
    capacities = np.arange(101)
    budgets = count * capacities // 100
    cumulative = np.r_[0, cohort.is_late.astype(int).cumsum().to_numpy()]
    chart = go.Figure()
    chart.add_scatter(x=capacities, y=cumulative[budgets] / total_late,
                      name="Risk prioritisation", mode="lines", line=dict(color="#2563eb"))
    chart.add_scatter(x=capacities, y=budgets / count, name="Random selection (expected)",
                      mode="lines", line=dict(color="#94a3b8", dash="dash"))
    chart.add_scatter(x=[capacity], y=[coverage], name="Selected capacity", mode="markers",
                      marker=dict(color="#e11d48", size=11))
    chart.update_layout(title="Review capacity and late-order coverage",
                        xaxis_title="Orders reviewed (%)", yaxis_title="Late orders captured",
                        yaxis_tickformat=".0%", yaxis_range=[0, 1.05],
                        legend=dict(orientation="h"), margin=dict(l=0, r=0, t=50, b=0))
    st.plotly_chart(chart, width="stretch")
with st.expander("Historical outcomes for the monitoring list"):
    outcomes = selected[["order_id", "risk_probability", "is_late"]].head(500).copy()
    outcomes["risk_probability"] = outcomes["risk_probability"].astype(float) * 100
    outcomes["is_late"] = outcomes.is_late.map({True: "Late", False: "On time"})
    st.dataframe(outcomes.rename(columns={"order_id": "Order ID", "is_late": "Historical outcome"}),
                 column_config={
                     "risk_probability": st.column_config.NumberColumn(
                         "Predicted late-delivery risk (%)", format="%.2f%%",
                         help="The model's pre-delivery risk estimate, not a certainty of late delivery.",
                     ),
                 },
                 hide_index=True, width="stretch")
with st.expander("Model evaluation details"):
    st.write("Logistic Regression was fitted on training orders. Validation orders set the fixed alert threshold. This page uses test orders only.")
    st.caption("Global test metrics below do not change with the customer-state or review-capacity filters.")
    metrics = metadata["test_metrics"]
    st.json({"Test average precision (PR-AUC)": metrics["pr_auc"],
             "Test ROC-AUC": metrics["roc_auc"], "Test Brier score": metrics["brier_score"],
             "Fixed alert threshold": metadata["alert_threshold"], "Scored at (UTC)": metadata["created_at"]})
    st.write(f"For the current capacity and customer-state selection: precision {percent(precision)}, recall {percent(coverage)}, F1 {percent(f1)}.")
    st.caption("The monitoring list uses the capacity budget, not the fixed alert threshold. Capacity is rounded down and score ties are broken by order ID.")
