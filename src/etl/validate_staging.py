"""Validate the raw staging layer."""

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
    """Validation query and expected value."""

    name: str
    expected_value: int
    query: str
    required: bool = True


@dataclass(frozen=True)
class CheckResult:
    name: str
    expected_value: int
    actual_value: int
    required: bool

    @property
    def status(self) -> str:
        if self.actual_value == self.expected_value:
            return "PASS"
        return "FAIL" if self.required else "OBSERVED"


ROW_COUNT_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition("row_count.stg_orders", 99_441, "SELECT COUNT(*) FROM staging.stg_orders"),
    CheckDefinition("row_count.stg_customers", 99_441, "SELECT COUNT(*) FROM staging.stg_customers"),
    CheckDefinition("row_count.stg_order_items", 112_650, "SELECT COUNT(*) FROM staging.stg_order_items"),
    CheckDefinition("row_count.stg_products", 32_951, "SELECT COUNT(*) FROM staging.stg_products"),
    CheckDefinition("row_count.stg_sellers", 3_095, "SELECT COUNT(*) FROM staging.stg_sellers"),
    CheckDefinition("row_count.stg_reviews", 99_224, "SELECT COUNT(*) FROM staging.stg_reviews"),
    CheckDefinition(
        "row_count.stg_category_translation",
        71,
        "SELECT COUNT(*) FROM staging.stg_category_translation",
    ),
)

KEY_AND_DOMAIN_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        "key_nulls.stg_orders.order_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_orders WHERE order_id IS NULL",
    ),
    CheckDefinition(
        "key_nulls.stg_customers.customer_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_customers WHERE customer_id IS NULL",
    ),
    CheckDefinition(
        "key_nulls.stg_order_items.order_id_or_item_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_order_items WHERE order_id IS NULL OR order_item_id IS NULL",
    ),
    CheckDefinition(
        "key_nulls.stg_products.product_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_products WHERE product_id IS NULL",
    ),
    CheckDefinition(
        "key_nulls.stg_sellers.seller_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_sellers WHERE seller_id IS NULL",
    ),
    CheckDefinition(
        "key_nulls.stg_category_translation.category",
        0,
        "SELECT COUNT(*) FROM staging.stg_category_translation WHERE product_category_name IS NULL",
    ),
    CheckDefinition(
        "key_nulls.stg_reviews.review_id_or_order_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_reviews WHERE review_id IS NULL OR order_id IS NULL",
    ),
    CheckDefinition(
        "duplicate_groups.stg_orders.order_id",
        0,
        "SELECT COUNT(*) FROM (SELECT order_id FROM staging.stg_orders GROUP BY order_id HAVING COUNT(*) > 1) duplicates",
    ),
    CheckDefinition(
        "duplicate_groups.stg_customers.customer_id",
        0,
        "SELECT COUNT(*) FROM (SELECT customer_id FROM staging.stg_customers GROUP BY customer_id HAVING COUNT(*) > 1) duplicates",
    ),
    CheckDefinition(
        "duplicate_groups.stg_order_items.order_id_and_item_id",
        0,
        "SELECT COUNT(*) FROM (SELECT order_id, order_item_id FROM staging.stg_order_items GROUP BY order_id, order_item_id HAVING COUNT(*) > 1) duplicates",
    ),
    CheckDefinition(
        "duplicate_groups.stg_products.product_id",
        0,
        "SELECT COUNT(*) FROM (SELECT product_id FROM staging.stg_products GROUP BY product_id HAVING COUNT(*) > 1) duplicates",
    ),
    CheckDefinition(
        "duplicate_groups.stg_sellers.seller_id",
        0,
        "SELECT COUNT(*) FROM (SELECT seller_id FROM staging.stg_sellers GROUP BY seller_id HAVING COUNT(*) > 1) duplicates",
    ),
    CheckDefinition(
        "duplicate_groups.stg_category_translation.category",
        0,
        "SELECT COUNT(*) FROM (SELECT product_category_name FROM staging.stg_category_translation GROUP BY product_category_name HAVING COUNT(*) > 1) duplicates",
    ),
    CheckDefinition(
        "domain.orders.invalid_status",
        0,
        "SELECT COUNT(*) FROM staging.stg_orders WHERE order_status IS NULL OR LOWER(BTRIM(order_status)) NOT IN ('created', 'approved', 'invoiced', 'processing', 'shipped', 'delivered', 'canceled', 'unavailable')",
    ),
    CheckDefinition(
        "domain.customers.invalid_state",
        0,
        "SELECT COUNT(*) FROM staging.stg_customers WHERE customer_state IS NULL OR UPPER(BTRIM(customer_state)) NOT IN ('AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO')",
    ),
    CheckDefinition(
        "domain.sellers.invalid_state",
        0,
        "SELECT COUNT(*) FROM staging.stg_sellers WHERE seller_state IS NULL OR UPPER(BTRIM(seller_state)) NOT IN ('AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO')",
    ),
    CheckDefinition(
        "domain.reviews.invalid_score",
        0,
        "SELECT COUNT(*) FROM staging.stg_reviews WHERE review_score IS NULL OR BTRIM(review_score) !~ '^[1-5]$'",
    ),
)

REFERENCE_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        "orphan.orders.customer_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_orders o LEFT JOIN staging.stg_customers c ON c.customer_id = o.customer_id WHERE o.customer_id IS NOT NULL AND c.customer_id IS NULL",
    ),
    CheckDefinition(
        "orphan.order_items.order_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_order_items i LEFT JOIN staging.stg_orders o ON o.order_id = i.order_id WHERE i.order_id IS NOT NULL AND o.order_id IS NULL",
    ),
    CheckDefinition(
        "orphan.order_items.product_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_order_items i LEFT JOIN staging.stg_products p ON p.product_id = i.product_id WHERE i.product_id IS NOT NULL AND p.product_id IS NULL",
    ),
    CheckDefinition(
        "orphan.order_items.seller_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_order_items i LEFT JOIN staging.stg_sellers s ON s.seller_id = i.seller_id WHERE i.seller_id IS NOT NULL AND s.seller_id IS NULL",
    ),
    CheckDefinition(
        "orphan.reviews.order_id",
        0,
        "SELECT COUNT(*) FROM staging.stg_reviews r LEFT JOIN staging.stg_orders o ON o.order_id = r.order_id WHERE r.order_id IS NOT NULL AND o.order_id IS NULL",
    ),
)

OBSERVATION_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        "reference.products.untranslated_category",
        13,
        "SELECT COUNT(*) FROM staging.stg_products p LEFT JOIN staging.stg_category_translation t ON t.product_category_name = p.product_category_name WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL",
        required=False,
    ),
    CheckDefinition(
        "delivery.delivered_without_actual_timestamp",
        8,
        "SELECT COUNT(*) FROM staging.stg_orders WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL",
        required=False,
    ),
)

ALL_CHECKS = ROW_COUNT_CHECKS + KEY_AND_DOMAIN_CHECKS + REFERENCE_CHECKS + OBSERVATION_CHECKS


def print_results(results: Sequence[CheckResult]) -> None:
    print("\nSTAGING VALIDATION")
    print("Check                                              | Expected | Actual   | Status")
    print("---------------------------------------------------+----------+----------+----------")
    for result in results:
        print(
            f"{result.name:<51} | {result.expected_value:>8,} | "
            f"{result.actual_value:>8,} | {result.status}"
        )


def run_check(cursor: psycopg.Cursor, definition: CheckDefinition) -> CheckResult:
    cursor.execute(definition.query)
    actual_value = int(cursor.fetchone()[0])
    return CheckResult(
        name=definition.name,
        expected_value=definition.expected_value,
        actual_value=actual_value,
        required=definition.required,
    )


def validate_staging() -> dict[str, int]:
    """Validate staging data against the source contract."""
    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            results = [run_check(cursor, definition) for definition in ALL_CHECKS]

    print_results(results)
    failures = [result for result in results if result.required and result.status == "FAIL"]
    if failures:
        failed_names = ", ".join(result.name for result in failures)
        raise RuntimeError(f"Staging validation failed: {failed_names}")

    return {result.name: result.actual_value for result in results}


def main() -> None:
    validate_staging()


if __name__ == "__main__":
    main()
