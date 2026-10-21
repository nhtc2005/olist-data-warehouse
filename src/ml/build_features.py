"""Build the order-level ML feature mart."""

from __future__ import annotations

import sys
from pathlib import Path

import psycopg

try:
    from etl.load_staging import connect_to_warehouse
except ModuleNotFoundError:
    SOURCE_DIR = Path(__file__).resolve().parents[1]
    if str(SOURCE_DIR) not in sys.path:
        sys.path.insert(0, str(SOURCE_DIR))
    from etl.load_staging import connect_to_warehouse


MART_SCHEMA = "mart"
FEATURE_TABLE = "order_delivery_ml_features"

DDL_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS mart",
    "DROP TABLE IF EXISTS mart.order_delivery_ml_features",
    """
    CREATE TABLE mart.order_delivery_ml_features (
        order_id TEXT PRIMARY KEY,
        purchase_date_key INTEGER NOT NULL,
        purchase_month SMALLINT NOT NULL CHECK (purchase_month BETWEEN 1 AND 12),
        purchase_weekday SMALLINT NOT NULL CHECK (purchase_weekday BETWEEN 1 AND 7),
        promised_lead_time_days NUMERIC(10, 2),
        customer_state CHAR(2) NOT NULL,
        has_out_of_state_seller BOOLEAN,
        item_count INTEGER NOT NULL CHECK (item_count >= 0),
        total_order_value NUMERIC(14, 2) NOT NULL CHECK (total_order_value >= 0),
        is_ml_eligible BOOLEAN NOT NULL,
        is_timeliness_eligible BOOLEAN NOT NULL,
        is_late BOOLEAN,
        CHECK (
            (is_timeliness_eligible AND is_late IS NOT NULL)
            OR (NOT is_timeliness_eligible AND is_late IS NULL)
        )
    )
    """,
    "CREATE INDEX idx_ml_features_purchase_date ON mart.order_delivery_ml_features(purchase_date_key)",
    "CREATE INDEX idx_ml_features_training_population ON mart.order_delivery_ml_features(is_ml_eligible, is_timeliness_eligible)",
)


LOAD_FEATURE_MART = """
WITH order_aggregates AS (
    SELECT
        s.order_id,
        COUNT(*)::integer AS item_count,
        BOOL_OR(seller.state_code <> customer.state_code) AS has_out_of_state_seller,
        SUM(s.item_revenue + s.freight_value)::numeric(14, 2) AS total_order_value
    FROM dw.fact_sales s
    JOIN dw.dim_seller seller ON seller.seller_key = s.seller_key
    JOIN dw.dim_customer customer ON customer.customer_key = s.customer_key
    GROUP BY s.order_id
)
INSERT INTO mart.order_delivery_ml_features (
    order_id,
    purchase_date_key,
    purchase_month,
    purchase_weekday,
    promised_lead_time_days,
    customer_state,
    has_out_of_state_seller,
    item_count,
    total_order_value,
    is_ml_eligible,
    is_timeliness_eligible,
    is_late
)
SELECT
    d.order_id,
    d.purchase_date_key,
    EXTRACT(MONTH FROM d.purchase_timestamp)::smallint,
    EXTRACT(ISODOW FROM d.purchase_timestamp)::smallint,
    CASE
        WHEN d.approved_timestamp IS NOT NULL
             AND d.estimated_delivery_timestamp >= d.approved_timestamp
        THEN round(
            (EXTRACT(EPOCH FROM (d.estimated_delivery_timestamp - d.approved_timestamp))
                / 86400.0)::numeric,
            2
        )
    END,
    customer.state_code,
    a.has_out_of_state_seller,
    COALESCE(a.item_count, 0),
    COALESCE(a.total_order_value, 0),
    (
        d.approved_timestamp IS NOT NULL
        AND d.estimated_delivery_timestamp >= d.approved_timestamp
        AND COALESCE(a.item_count, 0) > 0
    ),
    d.is_timeliness_eligible,
    d.is_late
FROM dw.fact_delivery d
JOIN dw.dim_customer customer ON customer.customer_key = d.customer_key
LEFT JOIN order_aggregates a ON a.order_id = d.order_id
ORDER BY d.order_id
"""


def _create_mart_objects(cursor: psycopg.Cursor) -> None:
    for statement in DDL_STATEMENTS:
        cursor.execute(statement)


def build_ml_features() -> dict[str, int]:
    """Rebuild the feature mart from the warehouse."""
    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            _create_mart_objects(cursor)
            cursor.execute(LOAD_FEATURE_MART)
            cursor.execute("SELECT COUNT(*) FROM mart.order_delivery_ml_features")
            row_count = int(cursor.fetchone()[0])
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM mart.order_delivery_ml_features
                WHERE is_ml_eligible AND is_timeliness_eligible
                """
            )
            training_row_count = int(cursor.fetchone()[0])

    return {
        "mart.order_delivery_ml_features": row_count,
        "training_population": training_row_count,
    }


def main() -> None:
    for name, row_count in build_ml_features().items():
        print(f"{name}: {row_count:,} rows")


if __name__ == "__main__":
    main()
