"""Database queries for the Streamlit dashboard."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]


def _connect() -> psycopg.Connection:
    load_dotenv(ROOT / ".env")
    required = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing database settings: " + ", ".join(missing))
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def _read_query(query: str, params: tuple[object, ...] = ()) -> pd.DataFrame:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column.name for column in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=columns)


def get_purchase_date_bounds() -> tuple[date, date]:
    """Return the available purchase-date range."""
    result = _read_query(
        """
        SELECT
            MIN(calendar_date) AS first_purchase_date,
            MAX(calendar_date) AS last_purchase_date
        FROM dw.fact_sales sales
        JOIN dw.dim_date dates ON dates.date_key = sales.purchase_date_key
        """
    ).iloc[0]
    if pd.isna(result["first_purchase_date"]) or pd.isna(result["last_purchase_date"]):
        raise RuntimeError("No sales data is available. Run the warehouse pipeline first.")
    return result["first_purchase_date"], result["last_purchase_date"]


def get_overview_metrics(start_date: date, end_date: date) -> pd.Series:
    """Return headline sales and delivery metrics for a purchase period."""
    return _read_query(
        """
        WITH selected_dates AS (
            SELECT date_key
            FROM dw.dim_date
            WHERE calendar_date BETWEEN %s AND %s
        )
        SELECT
            COALESCE((
                SELECT SUM(item_revenue + freight_value)
                FROM dw.fact_sales
                WHERE purchase_date_key IN (SELECT date_key FROM selected_dates)
            ), 0) AS revenue,
            (
                SELECT COUNT(DISTINCT order_id)
                FROM dw.fact_sales
                WHERE purchase_date_key IN (SELECT date_key FROM selected_dates)
            ) AS orders,
            (
                SELECT AVG(CASE WHEN is_late THEN 1.0 ELSE 0.0 END)
                FROM dw.fact_delivery
                WHERE purchase_date_key IN (SELECT date_key FROM selected_dates)
                  AND is_timeliness_eligible
            ) AS late_rate
        """,
        (start_date, end_date),
    ).iloc[0]


def get_monthly_sales(start_date: date, end_date: date) -> pd.DataFrame:
    """Return monthly revenue and distinct-order totals."""
    return _read_query(
        """
        SELECT
            DATE_TRUNC('month', dates.calendar_date)::date AS month,
            SUM(sales.item_revenue + sales.freight_value) AS revenue,
            COUNT(DISTINCT sales.order_id) AS orders
        FROM dw.fact_sales sales
        JOIN dw.dim_date dates ON dates.date_key = sales.purchase_date_key
        WHERE dates.calendar_date BETWEEN %s AND %s
        GROUP BY 1
        ORDER BY 1
        """,
        (start_date, end_date),
    )


def get_monthly_late_rate(start_date: date, end_date: date) -> pd.DataFrame:
    """Return monthly late-delivery rates for eligible orders."""
    return _read_query(
        """
        SELECT
            DATE_TRUNC('month', dates.calendar_date)::date AS month,
            COUNT(*) AS eligible_orders,
            AVG(CASE WHEN delivery.is_late THEN 1.0 ELSE 0.0 END) AS late_rate
        FROM dw.fact_delivery delivery
        JOIN dw.dim_date dates ON dates.date_key = delivery.purchase_date_key
        WHERE dates.calendar_date BETWEEN %s AND %s
          AND delivery.is_timeliness_eligible
        GROUP BY 1
        ORDER BY 1
        """,
        (start_date, end_date),
    )


def get_sales_by_category(start_date: date, end_date: date) -> pd.DataFrame:
    """Return the ten highest-revenue product categories."""
    return _read_query(
        """
        SELECT
            product.category_name_en AS category,
            SUM(sales.item_revenue + sales.freight_value) AS revenue,
            COUNT(DISTINCT sales.order_id) AS orders
        FROM dw.fact_sales sales
        JOIN dw.dim_date dates ON dates.date_key = sales.purchase_date_key
        JOIN dw.dim_product product ON product.product_key = sales.product_key
        WHERE dates.calendar_date BETWEEN %s AND %s
        GROUP BY 1
        ORDER BY revenue DESC
        LIMIT 10
        """,
        (start_date, end_date),
    )


def get_sales_by_customer_state(start_date: date, end_date: date) -> pd.DataFrame:
    """Return the ten highest-revenue customer states."""
    return _read_query(
        """
        SELECT
            customer.state_code AS customer_state,
            SUM(sales.item_revenue + sales.freight_value) AS revenue,
            COUNT(DISTINCT sales.order_id) AS orders
        FROM dw.fact_sales sales
        JOIN dw.dim_date dates ON dates.date_key = sales.purchase_date_key
        JOIN dw.dim_customer customer ON customer.customer_key = sales.customer_key
        WHERE dates.calendar_date BETWEEN %s AND %s
        GROUP BY 1
        ORDER BY revenue DESC
        LIMIT 10
        """,
        (start_date, end_date),
    )


def get_model_metadata() -> dict[str, object]:
    """Read metrics and threshold for the current model."""
    metadata_path = ROOT / "models" / "late_delivery_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError("Run src/ml/train_model.py before opening this page.")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def get_risk_customer_states() -> list[str]:
    """Return customer states represented in the current scores."""
    states = _read_query(
        """
        SELECT DISTINCT features.customer_state
        FROM mart.order_late_risk risk
        JOIN mart.order_delivery_ml_features features ON features.order_id = risk.order_id
        ORDER BY features.customer_state
        """
    )
    return states["customer_state"].tolist()


def get_risk_summary(population: str, customer_state: str) -> pd.Series:
    """Return score counts for the selected risk population."""
    return _read_query(
        """
        SELECT
            COUNT(*) AS scored_orders,
            COUNT(*) FILTER (WHERE risk.risk_band = 'high') AS high_risk_orders
        FROM mart.order_late_risk risk
        JOIN mart.order_delivery_ml_features features ON features.order_id = risk.order_id
        WHERE (%s = 'all' OR risk.population = %s)
          AND (%s = 'all' OR features.customer_state = %s)
        """,
        (population, population, customer_state, customer_state),
    ).iloc[0]


def get_monthly_high_risk(population: str, customer_state: str) -> pd.DataFrame:
    """Return monthly scored and high-risk order counts."""
    return _read_query(
        """
        SELECT
            DATE_TRUNC('month', dates.calendar_date)::date AS month,
            COUNT(*) AS scored_orders,
            COUNT(*) FILTER (WHERE risk.risk_band = 'high') AS high_risk_orders
        FROM mart.order_late_risk risk
        JOIN mart.order_delivery_ml_features features ON features.order_id = risk.order_id
        JOIN dw.dim_date dates ON dates.date_key = risk.purchase_date_key
        WHERE (%s = 'all' OR risk.population = %s)
          AND (%s = 'all' OR features.customer_state = %s)
        GROUP BY 1
        ORDER BY 1
        """,
        (population, population, customer_state, customer_state),
    )


def get_risk_orders(
    population: str, customer_state: str, only_high_risk: bool
) -> pd.DataFrame:
    """Return the highest-priority scored orders for the dashboard."""
    return _read_query(
        """
        SELECT
            risk.order_id,
            dates.calendar_date AS purchase_date,
            features.customer_state,
            features.promised_lead_time_days,
            features.item_count,
            features.total_order_value,
            features.has_out_of_state_seller,
            risk.risk_probability,
            risk.risk_band
        FROM mart.order_late_risk risk
        JOIN mart.order_delivery_ml_features features ON features.order_id = risk.order_id
        JOIN dw.dim_date dates ON dates.date_key = risk.purchase_date_key
        WHERE (%s = 'all' OR risk.population = %s)
          AND (%s = 'all' OR features.customer_state = %s)
          AND (NOT %s OR risk.risk_band = 'high')
        ORDER BY risk.risk_probability DESC, risk.order_id
        LIMIT 500
        """,
        (population, population, customer_state, customer_state, only_high_risk),
    )
