"""Load Olist CSV files into raw staging tables."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = ROOT / "data" / "raw"
STAGING_SCHEMA = "staging"
COPY_CHUNK_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StagingDataset:
    filename: str
    table_name: str
    columns: tuple[str, ...]

    @property
    def path(self) -> Path:
        return RAW_DATA_DIR / self.filename


DATASETS: tuple[StagingDataset, ...] = (
    StagingDataset(
        "olist_orders_dataset.csv",
        "stg_orders",
        (
            "order_id",
            "customer_id",
            "order_status",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ),
    ),
    StagingDataset(
        "olist_customers_dataset.csv",
        "stg_customers",
        (
            "customer_id",
            "customer_unique_id",
            "customer_zip_code_prefix",
            "customer_city",
            "customer_state",
        ),
    ),
    StagingDataset(
        "olist_order_items_dataset.csv",
        "stg_order_items",
        (
            "order_id",
            "order_item_id",
            "product_id",
            "seller_id",
            "shipping_limit_date",
            "price",
            "freight_value",
        ),
    ),
    StagingDataset(
        "olist_products_dataset.csv",
        "stg_products",
        (
            "product_id",
            "product_category_name",
            "product_name_lenght",
            "product_description_lenght",
            "product_photos_qty",
            "product_weight_g",
            "product_length_cm",
            "product_height_cm",
            "product_width_cm",
        ),
    ),
    StagingDataset(
        "olist_sellers_dataset.csv",
        "stg_sellers",
        (
            "seller_id",
            "seller_zip_code_prefix",
            "seller_city",
            "seller_state",
        ),
    ),
    StagingDataset(
        "olist_order_reviews_dataset.csv",
        "stg_reviews",
        (
            "review_id",
            "order_id",
            "review_score",
            "review_comment_title",
            "review_comment_message",
            "review_creation_date",
            "review_answer_timestamp",
        ),
    ),
    StagingDataset(
        "product_category_name_translation.csv",
        "stg_category_translation",
        ("product_category_name", "product_category_name_english"),
    ),
)


def connect_to_warehouse() -> psycopg.Connection:
    """Open a warehouse connection for Airflow or local runs."""
    airflow_connection = os.getenv("AIRFLOW_CONN_DW_POSTGRES")
    if airflow_connection:
        # psycopg expects a libpq URL, not SQLAlchemy's URL scheme.
        for sqlalchemy_scheme in ("postgresql+psycopg://", "postgresql+psycopg2://"):
            if airflow_connection.startswith(sqlalchemy_scheme):
                airflow_connection = airflow_connection.replace(
                    sqlalchemy_scheme, "postgresql://", 1
                )
                break
        return psycopg.connect(airflow_connection)

    try:
        from dotenv import load_dotenv
    except ImportError as error:
        raise RuntimeError(
            "Set AIRFLOW_CONN_DW_POSTGRES or install python-dotenv for a local run."
        ) from error

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


def _validate_source_files(datasets: Iterable[StagingDataset]) -> None:
    """Check source files and headers before loading."""
    for dataset in datasets:
        if not dataset.path.is_file():
            raise FileNotFoundError(f"Missing source CSV: {dataset.path}")

        with dataset.path.open("r", encoding="utf-8-sig", newline="") as source_file:
            try:
                header = tuple(next(csv.reader(source_file)))
            except StopIteration as error:
                raise ValueError(f"Source CSV is empty: {dataset.path}") from error

        if header != dataset.columns:
            raise ValueError(
                f"Unexpected header in {dataset.path.name}. "
                f"Expected {dataset.columns}, received {header}."
            )


def _create_staging_tables(cursor: psycopg.Cursor) -> None:
    cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(STAGING_SCHEMA)))

    for dataset in DATASETS:
        column_definitions = sql.SQL(", ").join(
            sql.SQL("{} TEXT").format(sql.Identifier(column))
            for column in dataset.columns
        )
        cursor.execute(
            sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} ({})").format(
                sql.Identifier(STAGING_SCHEMA),
                sql.Identifier(dataset.table_name),
                column_definitions,
            )
        )


def _truncate_staging_tables(cursor: psycopg.Cursor) -> None:
    tables = sql.SQL(", ").join(
        sql.SQL("{}.{}").format(
            sql.Identifier(STAGING_SCHEMA), sql.Identifier(dataset.table_name)
        )
        for dataset in DATASETS
    )
    cursor.execute(sql.SQL("TRUNCATE TABLE {}").format(tables))


def _copy_dataset(cursor: psycopg.Cursor, dataset: StagingDataset) -> int:
    columns = sql.SQL(", ").join(sql.Identifier(column) for column in dataset.columns)
    copy_statement = sql.SQL(
        "COPY {}.{} ({}) FROM STDIN WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8', NULL '')"
    ).format(
        sql.Identifier(STAGING_SCHEMA),
        sql.Identifier(dataset.table_name),
        columns,
    )

    with dataset.path.open("rb") as source_file:
        with cursor.copy(copy_statement) as copy:
            while chunk := source_file.read(COPY_CHUNK_SIZE_BYTES):
                copy.write(chunk)

    cursor.execute(
        sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
            sql.Identifier(STAGING_SCHEMA), sql.Identifier(dataset.table_name)
        )
    )
    return int(cursor.fetchone()[0])


def load_staging() -> dict[str, int]:
    """Reload staging tables from the source CSV files."""
    _validate_source_files(DATASETS)
    row_counts: dict[str, int] = {}

    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            _create_staging_tables(cursor)
            _truncate_staging_tables(cursor)
            for dataset in DATASETS:
                row_counts[dataset.table_name] = _copy_dataset(cursor, dataset)

    return row_counts


def main() -> None:
    for table_name, row_count in load_staging().items():
        print(f"{table_name}: {row_count:,} rows loaded")


if __name__ == "__main__":
    main()
