"""Validate the warehouse against staging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import psycopg

try:
    from etl.load_staging import connect_to_warehouse
except ModuleNotFoundError:
    from load_staging import connect_to_warehouse


@dataclass(frozen=True)
class CheckDefinition:
    """Warehouse reconciliation query."""

    name: str
    query: str
    required: bool = True


@dataclass(frozen=True)
class CheckResult:
    name: str
    actual_value: int
    required: bool

    @property
    def status(self) -> str:
        if self.actual_value == 0:
            return "PASS"
        return "FAIL" if self.required else "OBSERVED"


def _normalise_label(expression: str) -> str:
    return f"lower(regexp_replace(btrim({expression}), '[[:space:]]+', ' ', 'g'))"


DW_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        "row_count.dim_date",
        """
        WITH bounds AS (
            SELECT
                MIN(NULLIF(btrim(order_purchase_timestamp), '')::timestamp)::date AS first_date,
                MAX(NULLIF(btrim(order_estimated_delivery_date), '')::timestamp)::date AS last_date
            FROM staging.stg_orders
        )
        SELECT ABS(
            (SELECT (last_date - first_date) + 1 FROM bounds)
            - (SELECT COUNT(*) FROM dw.dim_date)
        )
        """,
    ),
    CheckDefinition(
        "row_count.dim_customer",
        """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_customers)
            - (SELECT COUNT(*) FROM dw.dim_customer)
        )
        """,
    ),
    CheckDefinition(
        "row_count.dim_seller",
        """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_sellers)
            - (SELECT COUNT(*) FROM dw.dim_seller)
        )
        """,
    ),
    CheckDefinition(
        "row_count.dim_product",
        """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_products)
            - (SELECT COUNT(*) FROM dw.dim_product)
        )
        """,
    ),
    CheckDefinition(
        "row_count.fact_sales",
        """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_order_items)
            - (SELECT COUNT(*) FROM dw.fact_sales)
        )
        """,
    ),
    CheckDefinition(
        "row_count.fact_delivery",
        """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_orders)
            - (SELECT COUNT(*) FROM dw.fact_delivery)
        )
        """,
    ),
    CheckDefinition(
        "grain.fact_sales.order_and_item",
        """
        SELECT COUNT(*) - COUNT(DISTINCT (order_id, order_item_id))
        FROM dw.fact_sales
        """,
    ),
    CheckDefinition(
        "grain.fact_delivery.order",
        "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM dw.fact_delivery",
    ),
    CheckDefinition(
        "measure.item_revenue",
        """
        SELECT CASE WHEN
            (SELECT COALESCE(SUM(NULLIF(btrim(price), '')::numeric(14, 2)), 0)
             FROM staging.stg_order_items)
            =
            (SELECT COALESCE(SUM(item_revenue), 0) FROM dw.fact_sales)
        THEN 0 ELSE 1 END
        """,
    ),
    CheckDefinition(
        "measure.freight_value",
        """
        SELECT CASE WHEN
            (SELECT COALESCE(SUM(NULLIF(btrim(freight_value), '')::numeric(14, 2)), 0)
             FROM staging.stg_order_items)
            =
            (SELECT COALESCE(SUM(freight_value), 0) FROM dw.fact_sales)
        THEN 0 ELSE 1 END
        """,
    ),
    CheckDefinition(
        "delivery.timeliness_eligible",
        """
        WITH staging_eligible AS (
            SELECT COUNT(*) AS row_count
            FROM staging.stg_orders
            WHERE lower(btrim(order_status)) = 'delivered'
              AND NULLIF(btrim(order_purchase_timestamp), '')::timestamp IS NOT NULL
              AND NULLIF(btrim(order_delivered_customer_date), '')::timestamp IS NOT NULL
              AND NULLIF(btrim(order_estimated_delivery_date), '')::timestamp IS NOT NULL
              AND NULLIF(btrim(order_delivered_customer_date), '')::timestamp
                    >= NULLIF(btrim(order_purchase_timestamp), '')::timestamp
        )
        SELECT ABS(
            (SELECT row_count FROM staging_eligible)
            - (SELECT COUNT(*) FROM dw.fact_delivery WHERE is_timeliness_eligible)
        )
        """,
    ),
    CheckDefinition(
        "delivery.temporal_anomaly",
        """
        WITH typed_orders AS (
            SELECT
                NULLIF(btrim(order_purchase_timestamp), '')::timestamp AS purchase_timestamp,
                NULLIF(btrim(order_approved_at), '')::timestamp AS approved_timestamp,
                NULLIF(btrim(order_delivered_carrier_date), '')::timestamp AS carrier_timestamp,
                NULLIF(btrim(order_delivered_customer_date), '')::timestamp AS actual_delivery_timestamp,
                NULLIF(btrim(order_estimated_delivery_date), '')::timestamp AS estimated_delivery_timestamp
            FROM staging.stg_orders
        ), expected AS (
            SELECT COUNT(*) AS row_count
            FROM typed_orders
            WHERE (approved_timestamp IS NOT NULL AND approved_timestamp < purchase_timestamp)
               OR (carrier_timestamp IS NOT NULL AND carrier_timestamp < purchase_timestamp)
               OR (carrier_timestamp IS NOT NULL AND actual_delivery_timestamp IS NOT NULL
                   AND carrier_timestamp > actual_delivery_timestamp)
               OR (actual_delivery_timestamp IS NOT NULL
                   AND actual_delivery_timestamp < purchase_timestamp)
               OR estimated_delivery_timestamp < purchase_timestamp
        )
        SELECT ABS(
            (SELECT row_count FROM expected)
            - (SELECT COUNT(*) FROM dw.fact_delivery WHERE has_temporal_anomaly)
        )
        """,
    ),
    CheckDefinition(
        "review.record_count",
        """
        WITH source_review_rows AS (
            SELECT DISTINCT order_id, review_id
            FROM staging.stg_reviews
        )
        SELECT ABS(
            (SELECT COUNT(*) FROM source_review_rows)
            - (SELECT COALESCE(SUM(review_record_count), 0) FROM dw.fact_delivery)
        )
        """,
    ),
    CheckDefinition(
        "product.unknown_or_untranslated_category",
        f"""
        WITH translations AS (
            SELECT {_normalise_label('product_category_name')} AS category_key
            FROM staging.stg_category_translation
        ), expected AS (
            SELECT COUNT(*) AS row_count
            FROM staging.stg_products p
            LEFT JOIN translations t
                ON t.category_key = {_normalise_label('p.product_category_name')}
            WHERE NULLIF(btrim(p.product_category_name), '') IS NULL
               OR t.category_key IS NULL
        )
        SELECT ABS(
            (SELECT row_count FROM expected)
            - (
                SELECT COUNT(*)
                FROM dw.dim_product
                WHERE category_name_en = 'Unknown / untranslated'
            )
        )
        """,
    ),
    CheckDefinition(
        "product.physical_anomaly",
        """
        WITH expected AS (
            SELECT COUNT(*) AS row_count
            FROM staging.stg_products
            WHERE (product_weight_g IS NOT NULL AND NULLIF(btrim(product_weight_g), '')::integer <= 0)
               OR (product_length_cm IS NOT NULL AND NULLIF(btrim(product_length_cm), '')::numeric <= 0)
               OR (product_height_cm IS NOT NULL AND NULLIF(btrim(product_height_cm), '')::numeric <= 0)
               OR (product_width_cm IS NOT NULL AND NULLIF(btrim(product_width_cm), '')::numeric <= 0)
        )
        SELECT ABS(
            (SELECT row_count FROM expected)
            - (SELECT COUNT(*) FROM dw.dim_product WHERE has_physical_anomaly)
        )
        """,
    ),
)


def print_results(results: Sequence[CheckResult]) -> None:
    print("\nDW VALIDATION")
    print("Check                                      | Difference | Status")
    print("-------------------------------------------+------------+----------")
    for result in results:
        print(f"{result.name:<42} | {result.actual_value:>10,} | {result.status}")


def run_check(cursor: psycopg.Cursor, definition: CheckDefinition) -> CheckResult:
    cursor.execute(definition.query)
    return CheckResult(
        name=definition.name,
        actual_value=int(cursor.fetchone()[0]),
        required=definition.required,
    )


def validate_dw() -> dict[str, int]:
    """Validate warehouse counts and reconciliations."""
    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            results = [run_check(cursor, definition) for definition in DW_CHECKS]

    print_results(results)
    failures = [result for result in results if result.required and result.status == "FAIL"]
    if failures:
        failed_names = ", ".join(result.name for result in failures)
        raise RuntimeError(f"DW validation failed: {failed_names}")

    return {result.name: result.actual_value for result in results}


def main() -> None:
    validate_dw()


if __name__ == "__main__":
    main()
