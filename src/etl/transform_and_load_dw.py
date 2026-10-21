"""Build the Olist warehouse from staging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import psycopg

try:
    from etl.load_staging import connect_to_warehouse
except ModuleNotFoundError:
    from load_staging import connect_to_warehouse


DW_SCHEMA = "dw"
UNKNOWN_CATEGORY_LABEL = "Unknown / untranslated"
VALID_ORDER_STATUSES = (
    "created",
    "approved",
    "invoiced",
    "processing",
    "shipped",
    "delivered",
    "canceled",
    "unavailable",
)
BRAZILIAN_STATE_CODES = (
    "AC",
    "AL",
    "AM",
    "AP",
    "BA",
    "CE",
    "DF",
    "ES",
    "GO",
    "MA",
    "MG",
    "MS",
    "MT",
    "PA",
    "PB",
    "PE",
    "PI",
    "PR",
    "RJ",
    "RN",
    "RO",
    "RR",
    "RS",
    "SC",
    "SE",
    "SP",
    "TO",
)

STATUS_SQL = ", ".join(f"'{status}'" for status in VALID_ORDER_STATUSES)
STATE_SQL = ", ".join(f"'{state}'" for state in BRAZILIAN_STATE_CODES)


@dataclass(frozen=True)
class InputCheck:
    """SQL check run before rebuilding the warehouse."""

    name: str
    query: str


def _normalise_label(expression: str) -> str:
    return f"lower(regexp_replace(btrim({expression}), '[[:space:]]+', ' ', 'g'))"


def _timestamp_format_check(table: str, column: str) -> str:
    return (
        f"SELECT COUNT(*) FROM staging.{table} "
        f"WHERE {column} IS NOT NULL AND btrim({column}) <> '' "
        f"AND btrim({column}) !~ "
        "'^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$'"
    )


PRE_TRANSFORM_CHECKS: tuple[InputCheck, ...] = (
    InputCheck(
        "required_source_keys",
        """
        SELECT COUNT(*)
        FROM (
            SELECT order_id AS value FROM staging.stg_orders
            UNION ALL SELECT customer_id FROM staging.stg_orders
            UNION ALL SELECT customer_id FROM staging.stg_customers
            UNION ALL SELECT order_id FROM staging.stg_order_items
            UNION ALL SELECT product_id FROM staging.stg_order_items
            UNION ALL SELECT seller_id FROM staging.stg_order_items
            UNION ALL SELECT product_id FROM staging.stg_products
            UNION ALL SELECT seller_id FROM staging.stg_sellers
            UNION ALL SELECT review_id FROM staging.stg_reviews
            UNION ALL SELECT order_id FROM staging.stg_reviews
        ) required_values
        WHERE value IS NULL OR btrim(value) = ''
        """,
    ),
    InputCheck(
        "required_order_and_item_timestamps",
        """
        SELECT COUNT(*)
        FROM (
            SELECT order_purchase_timestamp AS value FROM staging.stg_orders
            UNION ALL SELECT order_estimated_delivery_date FROM staging.stg_orders
            UNION ALL SELECT shipping_limit_date FROM staging.stg_order_items
        ) required_values
        WHERE value IS NULL OR btrim(value) = ''
        """,
    ),
    InputCheck(
        "orders.valid_normalised_status",
        f"""
        SELECT COUNT(*) FROM staging.stg_orders
        WHERE order_status IS NULL
           OR lower(btrim(order_status)) NOT IN ({STATUS_SQL})
        """,
    ),
    InputCheck(
        "customers.valid_normalised_state",
        f"""
        SELECT COUNT(*) FROM staging.stg_customers
        WHERE customer_state IS NULL
           OR upper(btrim(customer_state)) NOT IN ({STATE_SQL})
        """,
    ),
    InputCheck(
        "sellers.valid_normalised_state",
        f"""
        SELECT COUNT(*) FROM staging.stg_sellers
        WHERE seller_state IS NULL
           OR upper(btrim(seller_state)) NOT IN ({STATE_SQL})
        """,
    ),
    InputCheck(
        "reviews.valid_score",
        """
        SELECT COUNT(*) FROM staging.stg_reviews
        WHERE review_score IS NULL OR btrim(review_score) !~ '^[1-5]$'
        """,
    ),
    InputCheck(
        "order_items.integer_item_id",
        """
        SELECT COUNT(*) FROM staging.stg_order_items
        WHERE order_item_id IS NULL OR btrim(order_item_id) !~ '^[1-9][0-9]*$'
        """,
    ),
    InputCheck(
        "order_items.nonnegative_money",
        """
        SELECT COUNT(*) FROM staging.stg_order_items
        WHERE price IS NULL
           OR freight_value IS NULL
           OR btrim(price) !~ '^[0-9]+([.][0-9]+)?$'
           OR btrim(freight_value) !~ '^[0-9]+([.][0-9]+)?$'
        """,
    ),
    InputCheck(
        "products.integer_attributes",
        """
        SELECT COUNT(*) FROM staging.stg_products
        WHERE (product_name_lenght IS NOT NULL AND btrim(product_name_lenght) !~ '^[0-9]+$')
           OR (product_description_lenght IS NOT NULL AND btrim(product_description_lenght) !~ '^[0-9]+$')
           OR (product_photos_qty IS NOT NULL AND btrim(product_photos_qty) !~ '^[0-9]+$')
           OR (product_weight_g IS NOT NULL AND btrim(product_weight_g) !~ '^[0-9]+$')
           OR (product_length_cm IS NOT NULL AND btrim(product_length_cm) !~ '^[0-9]+([.][0-9]+)?$')
           OR (product_height_cm IS NOT NULL AND btrim(product_height_cm) !~ '^[0-9]+([.][0-9]+)?$')
           OR (product_width_cm IS NOT NULL AND btrim(product_width_cm) !~ '^[0-9]+([.][0-9]+)?$')
        """,
    ),
    InputCheck(
        "normalised_category_translation_keys_are_unique",
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT {_normalise_label('product_category_name')} AS category_key
            FROM staging.stg_category_translation
            GROUP BY {_normalise_label('product_category_name')}
            HAVING COUNT(*) > 1
        ) duplicate_keys
        """,
    ),
    InputCheck(
        "orders.order_purchase_timestamp_format",
        _timestamp_format_check("stg_orders", "order_purchase_timestamp"),
    ),
    InputCheck(
        "orders.order_approved_at_format",
        _timestamp_format_check("stg_orders", "order_approved_at"),
    ),
    InputCheck(
        "orders.order_delivered_carrier_date_format",
        _timestamp_format_check("stg_orders", "order_delivered_carrier_date"),
    ),
    InputCheck(
        "orders.order_delivered_customer_date_format",
        _timestamp_format_check("stg_orders", "order_delivered_customer_date"),
    ),
    InputCheck(
        "orders.order_estimated_delivery_date_format",
        _timestamp_format_check("stg_orders", "order_estimated_delivery_date"),
    ),
    InputCheck(
        "order_items.shipping_limit_date_format",
        _timestamp_format_check("stg_order_items", "shipping_limit_date"),
    ),
    InputCheck(
        "reviews.review_creation_date_format",
        _timestamp_format_check("stg_reviews", "review_creation_date"),
    ),
    InputCheck(
        "reviews.review_answer_timestamp_format",
        _timestamp_format_check("stg_reviews", "review_answer_timestamp"),
    ),
)


DDL_STATEMENTS: tuple[str, ...] = (
    "DROP SCHEMA IF EXISTS dw CASCADE",
    "CREATE SCHEMA dw",
    f"""
    CREATE TABLE dw.dim_date (
        date_key INTEGER PRIMARY KEY,
        calendar_date DATE NOT NULL UNIQUE,
        calendar_year SMALLINT NOT NULL,
        calendar_quarter SMALLINT NOT NULL CHECK (calendar_quarter BETWEEN 1 AND 4),
        calendar_month SMALLINT NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
        calendar_day SMALLINT NOT NULL CHECK (calendar_day BETWEEN 1 AND 31),
        iso_weekday SMALLINT NOT NULL CHECK (iso_weekday BETWEEN 1 AND 7),
        month_name TEXT NOT NULL,
        day_name TEXT NOT NULL,
        is_weekend BOOLEAN NOT NULL
    )
    """,
    f"""
    CREATE TABLE dw.dim_customer (
        customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        customer_id TEXT NOT NULL UNIQUE,
        customer_unique_id TEXT NOT NULL,
        zip_code_prefix TEXT NOT NULL,
        city_raw TEXT NOT NULL,
        city_normalized TEXT NOT NULL,
        state_code CHAR(2) NOT NULL CHECK (state_code IN ({STATE_SQL}))
    )
    """,
    f"""
    CREATE TABLE dw.dim_seller (
        seller_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        seller_id TEXT NOT NULL UNIQUE,
        zip_code_prefix TEXT NOT NULL,
        city_raw TEXT NOT NULL,
        city_normalized TEXT NOT NULL,
        state_code CHAR(2) NOT NULL CHECK (state_code IN ({STATE_SQL}))
    )
    """,
    """
    CREATE TABLE dw.dim_product (
        product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        product_id TEXT NOT NULL UNIQUE,
        category_name_raw TEXT,
        category_name_normalized TEXT,
        category_name_en TEXT NOT NULL,
        product_name_length INTEGER,
        product_description_length INTEGER,
        product_photos_qty INTEGER,
        weight_g INTEGER CHECK (weight_g IS NULL OR weight_g > 0),
        length_cm NUMERIC(10, 2) CHECK (length_cm IS NULL OR length_cm > 0),
        height_cm NUMERIC(10, 2) CHECK (height_cm IS NULL OR height_cm > 0),
        width_cm NUMERIC(10, 2) CHECK (width_cm IS NULL OR width_cm > 0),
        has_missing_category BOOLEAN NOT NULL,
        has_physical_anomaly BOOLEAN NOT NULL
    )
    """,
    f"""
    CREATE TABLE dw.fact_sales (
        order_id TEXT NOT NULL,
        order_item_id INTEGER NOT NULL CHECK (order_item_id > 0),
        customer_key BIGINT NOT NULL REFERENCES dw.dim_customer(customer_key),
        product_key BIGINT NOT NULL REFERENCES dw.dim_product(product_key),
        seller_key BIGINT NOT NULL REFERENCES dw.dim_seller(seller_key),
        purchase_date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
        shipping_limit_timestamp TIMESTAMP NOT NULL,
        item_revenue NUMERIC(14, 2) NOT NULL CHECK (item_revenue >= 0),
        freight_value NUMERIC(14, 2) NOT NULL CHECK (freight_value >= 0),
        quantity SMALLINT NOT NULL DEFAULT 1 CHECK (quantity = 1),
        PRIMARY KEY (order_id, order_item_id)
    )
    """,
    f"""
    CREATE TABLE dw.fact_delivery (
        order_id TEXT PRIMARY KEY,
        customer_key BIGINT NOT NULL REFERENCES dw.dim_customer(customer_key),
        order_status TEXT NOT NULL CHECK (order_status IN ({STATUS_SQL})),
        purchase_date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
        approval_date_key INTEGER REFERENCES dw.dim_date(date_key),
        actual_delivery_date_key INTEGER REFERENCES dw.dim_date(date_key),
        estimated_delivery_date_key INTEGER NOT NULL REFERENCES dw.dim_date(date_key),
        purchase_timestamp TIMESTAMP NOT NULL,
        approved_timestamp TIMESTAMP,
        actual_delivery_timestamp TIMESTAMP,
        estimated_delivery_timestamp TIMESTAMP NOT NULL,
        is_timeliness_eligible BOOLEAN NOT NULL,
        is_late BOOLEAN,
        delivery_delay_days NUMERIC(10, 2),
        has_temporal_anomaly BOOLEAN NOT NULL,
        review_avg_score NUMERIC(3, 2) CHECK (
            review_avg_score IS NULL OR review_avg_score BETWEEN 1 AND 5
        ),
        review_record_count SMALLINT NOT NULL DEFAULT 0 CHECK (review_record_count >= 0),
        CHECK (
            (is_timeliness_eligible AND is_late IS NOT NULL AND delivery_delay_days IS NOT NULL)
            OR
            (NOT is_timeliness_eligible AND is_late IS NULL AND delivery_delay_days IS NULL)
        )
    )
    """,
    "CREATE INDEX idx_fact_sales_customer_key ON dw.fact_sales(customer_key)",
    "CREATE INDEX idx_fact_sales_product_key ON dw.fact_sales(product_key)",
    "CREATE INDEX idx_fact_sales_seller_key ON dw.fact_sales(seller_key)",
    "CREATE INDEX idx_fact_sales_purchase_date_key ON dw.fact_sales(purchase_date_key)",
    "CREATE INDEX idx_fact_delivery_customer_key ON dw.fact_delivery(customer_key)",
    "CREATE INDEX idx_fact_delivery_purchase_date_key ON dw.fact_delivery(purchase_date_key)",
    "CREATE INDEX idx_fact_delivery_status ON dw.fact_delivery(order_status)",
)


LOAD_DATE_DIMENSION = """
WITH bounds AS (
    SELECT
        MIN(NULLIF(btrim(order_purchase_timestamp), '')::timestamp)::date AS first_date,
        MAX(NULLIF(btrim(order_estimated_delivery_date), '')::timestamp)::date AS last_date
    FROM staging.stg_orders
)
INSERT INTO dw.dim_date (
    date_key,
    calendar_date,
    calendar_year,
    calendar_quarter,
    calendar_month,
    calendar_day,
    iso_weekday,
    month_name,
    day_name,
    is_weekend
)
SELECT
    to_char(calendar_date, 'YYYYMMDD')::integer,
    calendar_date,
    EXTRACT(YEAR FROM calendar_date)::smallint,
    EXTRACT(QUARTER FROM calendar_date)::smallint,
    EXTRACT(MONTH FROM calendar_date)::smallint,
    EXTRACT(DAY FROM calendar_date)::smallint,
    EXTRACT(ISODOW FROM calendar_date)::smallint,
    trim(to_char(calendar_date, 'Month')),
    trim(to_char(calendar_date, 'Day')),
    EXTRACT(ISODOW FROM calendar_date) IN (6, 7)
FROM bounds
CROSS JOIN LATERAL generate_series(first_date, last_date, interval '1 day') AS dates(calendar_date)
"""

LOAD_CUSTOMER_DIMENSION = """
INSERT INTO dw.dim_customer (
    customer_id,
    customer_unique_id,
    zip_code_prefix,
    city_raw,
    city_normalized,
    state_code
)
SELECT
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    lower(regexp_replace(btrim(customer_city), '[[:space:]]+', ' ', 'g')),
    upper(btrim(customer_state))
FROM staging.stg_customers
ORDER BY customer_id
"""

LOAD_SELLER_DIMENSION = """
INSERT INTO dw.dim_seller (
    seller_id,
    zip_code_prefix,
    city_raw,
    city_normalized,
    state_code
)
SELECT
    seller_id,
    seller_zip_code_prefix,
    seller_city,
    lower(regexp_replace(btrim(seller_city), '[[:space:]]+', ' ', 'g')),
    upper(btrim(seller_state))
FROM staging.stg_sellers
ORDER BY seller_id
"""

LOAD_PRODUCT_DIMENSION = f"""
WITH translations AS (
    SELECT
        {_normalise_label('product_category_name')} AS category_key,
        NULLIF(btrim(product_category_name_english), '') AS category_name_en
    FROM staging.stg_category_translation
),
prepared_products AS (
    SELECT
        p.product_id,
        NULLIF(btrim(p.product_category_name), '') AS category_name_raw,
        CASE
            WHEN NULLIF(btrim(p.product_category_name), '') IS NULL THEN NULL
            ELSE {_normalise_label('p.product_category_name')}
        END AS category_name_normalized,
        NULLIF(btrim(p.product_name_lenght), '')::integer AS product_name_length,
        NULLIF(btrim(p.product_description_lenght), '')::integer AS product_description_length,
        NULLIF(btrim(p.product_photos_qty), '')::integer AS product_photos_qty,
        NULLIF(btrim(p.product_weight_g), '')::integer AS weight_g_raw,
        NULLIF(btrim(p.product_length_cm), '')::numeric(10, 2) AS length_cm_raw,
        NULLIF(btrim(p.product_height_cm), '')::numeric(10, 2) AS height_cm_raw,
        NULLIF(btrim(p.product_width_cm), '')::numeric(10, 2) AS width_cm_raw
    FROM staging.stg_products p
)
INSERT INTO dw.dim_product (
    product_id,
    category_name_raw,
    category_name_normalized,
    category_name_en,
    product_name_length,
    product_description_length,
    product_photos_qty,
    weight_g,
    length_cm,
    height_cm,
    width_cm,
    has_missing_category,
    has_physical_anomaly
)
SELECT
    p.product_id,
    p.category_name_raw,
    p.category_name_normalized,
    COALESCE(t.category_name_en, '{UNKNOWN_CATEGORY_LABEL}'),
    p.product_name_length,
    p.product_description_length,
    p.product_photos_qty,
    CASE WHEN p.weight_g_raw > 0 THEN p.weight_g_raw END,
    CASE WHEN p.length_cm_raw > 0 THEN p.length_cm_raw END,
    CASE WHEN p.height_cm_raw > 0 THEN p.height_cm_raw END,
    CASE WHEN p.width_cm_raw > 0 THEN p.width_cm_raw END,
    p.category_name_raw IS NULL,
    COALESCE(p.weight_g_raw <= 0, FALSE)
        OR COALESCE(p.length_cm_raw <= 0, FALSE)
        OR COALESCE(p.height_cm_raw <= 0, FALSE)
        OR COALESCE(p.width_cm_raw <= 0, FALSE)
FROM prepared_products p
LEFT JOIN translations t ON t.category_key = p.category_name_normalized
ORDER BY p.product_id
"""

LOAD_SALES_FACT = """
WITH typed_orders AS (
    SELECT
        order_id,
        customer_id,
        NULLIF(btrim(order_purchase_timestamp), '')::timestamp AS purchase_timestamp
    FROM staging.stg_orders
),
typed_items AS (
    SELECT
        order_id,
        NULLIF(btrim(order_item_id), '')::integer AS order_item_id,
        product_id,
        seller_id,
        NULLIF(btrim(shipping_limit_date), '')::timestamp AS shipping_limit_timestamp,
        NULLIF(btrim(price), '')::numeric(14, 2) AS item_revenue,
        NULLIF(btrim(freight_value), '')::numeric(14, 2) AS freight_value
    FROM staging.stg_order_items
)
INSERT INTO dw.fact_sales (
    order_id,
    order_item_id,
    customer_key,
    product_key,
    seller_key,
    purchase_date_key,
    shipping_limit_timestamp,
    item_revenue,
    freight_value,
    quantity
)
SELECT
    i.order_id,
    i.order_item_id,
    c.customer_key,
    p.product_key,
    s.seller_key,
    to_char(o.purchase_timestamp::date, 'YYYYMMDD')::integer,
    i.shipping_limit_timestamp,
    i.item_revenue,
    i.freight_value,
    1
FROM typed_items i
JOIN typed_orders o ON o.order_id = i.order_id
JOIN dw.dim_customer c ON c.customer_id = o.customer_id
JOIN dw.dim_product p ON p.product_id = i.product_id
JOIN dw.dim_seller s ON s.seller_id = i.seller_id
ORDER BY i.order_id, i.order_item_id
"""

LOAD_DELIVERY_FACT = """
WITH typed_orders AS (
    SELECT
        order_id,
        customer_id,
        lower(btrim(order_status)) AS order_status,
        NULLIF(btrim(order_purchase_timestamp), '')::timestamp AS purchase_timestamp,
        NULLIF(btrim(order_approved_at), '')::timestamp AS approved_timestamp,
        NULLIF(btrim(order_delivered_carrier_date), '')::timestamp AS carrier_timestamp_raw,
        NULLIF(btrim(order_delivered_customer_date), '')::timestamp AS actual_delivery_timestamp,
        NULLIF(btrim(order_estimated_delivery_date), '')::timestamp AS estimated_delivery_timestamp
    FROM staging.stg_orders
),
deduplicated_review_rows AS (
    SELECT DISTINCT ON (order_id, review_id)
        order_id,
        review_id,
        NULLIF(btrim(review_score), '')::numeric(3, 2) AS review_score
    FROM staging.stg_reviews
    ORDER BY order_id, review_id, review_answer_timestamp DESC NULLS LAST,
        review_creation_date DESC NULLS LAST
),
reviews_by_order AS (
    SELECT
        order_id,
        AVG(review_score)::numeric(3, 2) AS review_avg_score,
        COUNT(*)::smallint AS review_record_count
    FROM deduplicated_review_rows
    GROUP BY order_id
),
prepared_orders AS (
    SELECT
        o.*,
        o.carrier_timestamp_raw IS NOT NULL
            AND o.carrier_timestamp_raw < o.purchase_timestamp AS carrier_before_purchase,
        o.carrier_timestamp_raw IS NOT NULL
            AND o.actual_delivery_timestamp IS NOT NULL
            AND o.carrier_timestamp_raw > o.actual_delivery_timestamp AS carrier_after_delivery,
        o.approved_timestamp IS NOT NULL AND o.approved_timestamp < o.purchase_timestamp
            AS approval_before_purchase,
        o.actual_delivery_timestamp IS NOT NULL
            AND o.actual_delivery_timestamp < o.purchase_timestamp AS delivery_before_purchase,
        o.estimated_delivery_timestamp < o.purchase_timestamp AS estimate_before_purchase
    FROM typed_orders o
),
fact_rows AS (
    SELECT
        o.*,
        (
            o.carrier_before_purchase
            OR o.carrier_after_delivery
            OR o.approval_before_purchase
            OR o.delivery_before_purchase
            OR o.estimate_before_purchase
        ) AS has_temporal_anomaly,
        (
            o.order_status = 'delivered'
            AND o.purchase_timestamp IS NOT NULL
            AND o.actual_delivery_timestamp IS NOT NULL
            AND o.estimated_delivery_timestamp IS NOT NULL
            AND o.actual_delivery_timestamp >= o.purchase_timestamp
        ) AS is_timeliness_eligible
    FROM prepared_orders o
)
INSERT INTO dw.fact_delivery (
    order_id,
    customer_key,
    order_status,
    purchase_date_key,
    approval_date_key,
    actual_delivery_date_key,
    estimated_delivery_date_key,
    purchase_timestamp,
    approved_timestamp,
    actual_delivery_timestamp,
    estimated_delivery_timestamp,
    is_timeliness_eligible,
    is_late,
    delivery_delay_days,
    has_temporal_anomaly,
    review_avg_score,
    review_record_count
)
SELECT
    o.order_id,
    c.customer_key,
    o.order_status,
    to_char(o.purchase_timestamp::date, 'YYYYMMDD')::integer,
    CASE WHEN o.approved_timestamp IS NOT NULL
        THEN to_char(o.approved_timestamp::date, 'YYYYMMDD')::integer END,
    CASE WHEN o.actual_delivery_timestamp IS NOT NULL
        THEN to_char(o.actual_delivery_timestamp::date, 'YYYYMMDD')::integer END,
    to_char(o.estimated_delivery_timestamp::date, 'YYYYMMDD')::integer,
    o.purchase_timestamp,
    o.approved_timestamp,
    o.actual_delivery_timestamp,
    o.estimated_delivery_timestamp,
    o.is_timeliness_eligible,
    CASE WHEN o.is_timeliness_eligible
        THEN o.actual_delivery_timestamp > o.estimated_delivery_timestamp END,
    CASE WHEN o.is_timeliness_eligible THEN
        round(
            (EXTRACT(EPOCH FROM (o.actual_delivery_timestamp - o.estimated_delivery_timestamp))
                / 86400.0)::numeric,
            2
        )
    END,
    o.has_temporal_anomaly,
    r.review_avg_score,
    COALESCE(r.review_record_count, 0)
FROM fact_rows o
JOIN dw.dim_customer c ON c.customer_id = o.customer_id
LEFT JOIN reviews_by_order r ON r.order_id = o.order_id
ORDER BY o.order_id
"""

DW_TABLES = (
    "dim_date",
    "dim_customer",
    "dim_seller",
    "dim_product",
    "fact_sales",
    "fact_delivery",
)


def _run_pre_transform_checks(cursor: psycopg.Cursor) -> None:
    failures: list[str] = []
    for check in PRE_TRANSFORM_CHECKS:
        cursor.execute(check.query)
        violations = int(cursor.fetchone()[0])
        print(f"{check.name}: {violations:,} violation(s)")
        if violations:
            failures.append(f"{check.name}={violations}")

    if failures:
        raise RuntimeError("DW pre-transform validation failed: " + ", ".join(failures))


def _rebuild_dw_schema(cursor: psycopg.Cursor) -> None:
    for statement in DDL_STATEMENTS:
        cursor.execute(statement)


def _load_dw(cursor: psycopg.Cursor) -> None:
    cursor.execute(LOAD_DATE_DIMENSION)
    cursor.execute(LOAD_CUSTOMER_DIMENSION)
    cursor.execute(LOAD_SELLER_DIMENSION)
    cursor.execute(LOAD_PRODUCT_DIMENSION)
    cursor.execute(LOAD_SALES_FACT)
    cursor.execute(LOAD_DELIVERY_FACT)


def _row_counts(cursor: psycopg.Cursor) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in DW_TABLES:
        cursor.execute(f"SELECT COUNT(*) FROM {DW_SCHEMA}.{table_name}")
        counts[table_name] = int(cursor.fetchone()[0])
    return counts


def transform_and_load_dw() -> dict[str, int]:
    """Rebuild the warehouse from staging."""
    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            _run_pre_transform_checks(cursor)
            _rebuild_dw_schema(cursor)
            _load_dw(cursor)
            counts = _row_counts(cursor)

    return counts


def main() -> None:
    for table_name, row_count in transform_and_load_dw().items():
        print(f"dw.{table_name}: {row_count:,} rows loaded")


if __name__ == "__main__":
    main()
