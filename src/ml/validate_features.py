"""Validate the ML feature mart."""

from __future__ import annotations

from dataclasses import dataclass
import sys
from pathlib import Path
from typing import Sequence

import psycopg

try:
    from etl.load_staging import connect_to_warehouse
except ModuleNotFoundError:
    SOURCE_DIR = Path(__file__).resolve().parents[1]
    if str(SOURCE_DIR) not in sys.path:
        sys.path.insert(0, str(SOURCE_DIR))
    from etl.load_staging import connect_to_warehouse


@dataclass(frozen=True)
class CheckDefinition:
    """Feature-mart validation query."""

    name: str
    query: str


@dataclass(frozen=True)
class CheckResult:
    name: str
    actual_value: int

    @property
    def status(self) -> str:
        return "PASS" if self.actual_value == 0 else "FAIL"


FEATURE_CHECKS: tuple[CheckDefinition, ...] = (
    CheckDefinition(
        "row_count.matches_fact_delivery",
        """
        SELECT ABS(
            (SELECT COUNT(*) FROM dw.fact_delivery)
            - (SELECT COUNT(*) FROM mart.order_delivery_ml_features)
        )
        """,
    ),
    CheckDefinition(
        "grain.one_row_per_order",
        """
        SELECT COUNT(*) - COUNT(DISTINCT order_id)
        FROM mart.order_delivery_ml_features
        """,
    ),
    CheckDefinition(
        "measure.order_value_matches_fact_sales",
        """
        SELECT CASE WHEN
            (SELECT COALESCE(SUM(item_revenue + freight_value), 0) FROM dw.fact_sales)
            =
            (SELECT COALESCE(SUM(total_order_value), 0) FROM mart.order_delivery_ml_features)
        THEN 0 ELSE 1 END
        """,
    ),
    CheckDefinition(
        "label.matches_fact_delivery",
        """
        SELECT COUNT(*)
        FROM mart.order_delivery_ml_features m
        JOIN dw.fact_delivery d ON d.order_id = m.order_id
        WHERE m.is_timeliness_eligible IS DISTINCT FROM d.is_timeliness_eligible
           OR m.is_late IS DISTINCT FROM d.is_late
        """,
    ),
    CheckDefinition(
        "eligible_training_rows_have_promised_lead_time_and_order_items",
        """
        SELECT COUNT(*)
        FROM mart.order_delivery_ml_features
        WHERE is_ml_eligible
          AND (
              promised_lead_time_days IS NULL
              OR item_count = 0
          )
        """,
    ),
    CheckDefinition(
        "no_outcome_columns_in_mart",
        """
        SELECT COUNT(*)
        FROM information_schema.columns
        WHERE table_schema = 'mart'
          AND table_name = 'order_delivery_ml_features'
          AND column_name IN (
              'actual_delivery_timestamp',
              'delivery_delay_days',
              'review_avg_score',
              'review_record_count',
              'order_status',
              'carrier_timestamp'
          )
        """,
    ),
)


def print_results(results: Sequence[CheckResult]) -> None:
    print("\nML FEATURE MART VALIDATION")
    print("Check                                                    | Difference | Status")
    print("---------------------------------------------------------+------------+----------")
    for result in results:
        print(f"{result.name:<56} | {result.actual_value:>10,} | {result.status}")


def validate_ml_features() -> dict[str, int]:
    """Validate feature-mart grain, values, and labels."""
    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            results: list[CheckResult] = []
            for definition in FEATURE_CHECKS:
                cursor.execute(definition.query)
                results.append(
                    CheckResult(definition.name, int(cursor.fetchone()[0]))
                )

    print_results(results)
    failures = [result.name for result in results if result.status == "FAIL"]
    if failures:
        raise RuntimeError("ML feature mart validation failed: " + ", ".join(failures))

    return {result.name: result.actual_value for result in results}


def main() -> None:
    validate_ml_features()


if __name__ == "__main__":
    main()
