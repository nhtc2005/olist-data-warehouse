"""Profile the Olist source CSV files."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = ROOT / "data" / "raw"
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"

DATASETS = {
    "orders": ("olist_orders_dataset.csv", ["order_id"]),
    "customers": ("olist_customers_dataset.csv", ["customer_id"]),
    "order_items": ("olist_order_items_dataset.csv", ["order_id", "order_item_id"]),
    "products": ("olist_products_dataset.csv", ["product_id"]),
    "sellers": ("olist_sellers_dataset.csv", ["seller_id"]),
    "reviews": ("olist_order_reviews_dataset.csv", ["review_id"]),
    "category_translation": (
        "product_category_name_translation.csv",
        ["product_category_name"],
    ),
}

CATEGORICAL_COLUMNS = {
    "orders": ("order_status",),
    "customers": ("customer_state", "customer_city"),
    "products": ("product_category_name",),
    "sellers": ("seller_state", "seller_city"),
    "category_translation": (
        "product_category_name",
        "product_category_name_english",
    ),
}

NUMERIC_COLUMNS = {
    "order_items": ("order_item_id", "price", "freight_value"),
    "products": (
        "product_name_lenght",
        "product_description_lenght",
        "product_photos_qty",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ),
    "reviews": ("review_score",),
}

TIMESTAMP_COLUMNS = {
    "orders": (
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ),
    "order_items": ("shipping_limit_date",),
    "reviews": ("review_creation_date", "review_answer_timestamp"),
}

KNOWN_ORDER_STATUSES = frozenset(
    {
        "approved",
        "canceled",
        "created",
        "delivered",
        "invoiced",
        "processing",
        "shipped",
        "unavailable",
    }
)

BRAZILIAN_STATE_CODES = frozenset(
    {
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
    }
)

SHOW_ALL_CATEGORIES_WHEN_AT_MOST = 100
TOP_CATEGORY_VALUES = 20
MAX_VARIANT_ROWS = 20


def read_dataset(filename: str) -> pd.DataFrame:
    """Load a CSV as strings to preserve IDs and ZIP prefixes."""
    return pd.read_csv(RAW_DATA_DIR / filename, dtype="string")


def print_section(title: str) -> None:
    print(f"\n{title}")


def print_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    rendered_rows = [[str(value) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in rendered_rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]

    def render(row: Sequence[str]) -> str:
        return " | ".join(value.ljust(width) for value, width in zip(row, widths))

    print(render(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rendered_rows:
        print(render(row))


def format_number(value: float | int | None) -> str:
    if value is None or pd.isna(value):
        return "-"
    rendered = f"{float(value):,.2f}"
    return rendered.rstrip("0").rstrip(".")


def present_value_mask(values: pd.Series) -> pd.Series:
    return values.notna() & values.str.strip().ne("").fillna(False)


def comparison_key(values: pd.Series) -> pd.Series:
    """Return a case- and whitespace-insensitive key for profiling only."""
    return values.str.strip().str.replace(r"\s+", " ", regex=True).str.casefold()


def parse_timestamp(values: pd.Series) -> pd.Series:
    """Parse timestamps using the documented source format."""
    return pd.to_datetime(values, format=TIMESTAMP_FORMAT, errors="coerce")


def dataset_profile_row(
    name: str, frame: pd.DataFrame, key_columns: list[str]
) -> tuple[str, str, str, str, str, str]:
    key_values_present = pd.DataFrame(
        {column: present_value_mask(frame[column]) for column in key_columns}
    )
    missing_key_values = int((~key_values_present.all(axis=1)).sum())
    duplicate_key_rows = int(frame.duplicated(key_columns, keep=False).sum())
    return (
        name,
        f"{len(frame):,}",
        str(len(frame.columns)),
        ", ".join(key_columns),
        f"{missing_key_values:,}",
        f"{duplicate_key_rows:,}",
    )


def nullable_column_rows(name: str, frame: pd.DataFrame) -> list[tuple[str, str, str]]:
    null_counts = frame.isna().sum()
    nullable_columns = null_counts[null_counts > 0]
    if nullable_columns.empty:
        return [(name, "none", "-")]
    return [
        (name, str(column), f"{int(count):,}")
        for column, count in nullable_columns.items()
    ]


def blank_value_rows(frames: dict[str, pd.DataFrame]) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for dataset, frame in frames.items():
        for column in frame.columns:
            values = frame[column]
            blank_values = values.notna() & values.str.strip().eq("").fillna(False)
            count = int(blank_values.sum())
            if count:
                rows.append((dataset, str(column), f"{count:,}"))
    return rows or [("none", "none", "0")]


def missing_reference_row(
    label: str,
    child: pd.DataFrame,
    child_column: str,
    parent: pd.DataFrame,
    parent_column: str,
) -> tuple[str, str, str]:
    values_to_check = child[child_column].dropna()
    parent_values = set(parent[parent_column].dropna())
    missing = int((~values_to_check.isin(parent_values)).sum())
    return label, f"{missing:,}", f"{len(values_to_check):,}"


def print_categorical_profile(frames: dict[str, pd.DataFrame]) -> None:
    print_section("4. CATEGORICAL LABELS AND NORMALISATION CANDIDATES")
    summary_rows: list[tuple[str, str, str, str, str, str, str]] = []
    value_reports: list[tuple[str, str, pd.Series, int]] = []
    variant_rows: list[tuple[str, str, str, str]] = []

    for dataset, columns in CATEGORICAL_COLUMNS.items():
        frame = frames[dataset]
        for column in columns:
            values = frame[column]
            present = present_value_mask(values)
            non_null_values = values.loc[present]
            keys = comparison_key(non_null_values)
            whitespace_changed = non_null_values.ne(
                non_null_values.str.strip().str.replace(r"\s+", " ", regex=True)
            )
            raw_variants = pd.DataFrame({"raw": non_null_values, "key": keys})
            variants_per_key = raw_variants.groupby("key")["raw"].nunique()
            collision_keys = variants_per_key[variants_per_key > 1].index

            summary_rows.append(
                (
                    dataset,
                    column,
                    f"{int(present.sum()):,}",
                    f"{int(values.isna().sum()):,}",
                    f"{int(non_null_values.nunique()):,}",
                    f"{int(keys.nunique()):,}",
                    f"{int(whitespace_changed.sum()):,} / {len(collision_keys):,}",
                )
            )
            value_reports.append(
                (dataset, column, non_null_values.value_counts(), len(collision_keys))
            )

            for key in collision_keys[:MAX_VARIANT_ROWS]:
                raw_counts = raw_variants.loc[raw_variants["key"].eq(key), "raw"].value_counts()
                variants = "; ".join(
                    f"{raw!r} ({count:,})" for raw, count in raw_counts.items()
                )
                variant_rows.append((dataset, column, str(key), variants))

    print_table(
        (
            "Dataset",
            "Column",
            "Present",
            "NULL",
            "Raw labels",
            "Comparison keys",
            "Whitespace rows / variant keys",
        ),
        summary_rows,
    )

    print("\nRaw label frequencies (all values when <= 100; otherwise top 20):")
    for dataset, column, counts, collision_count in value_reports:
        print(
            f"\n{dataset}.{column} "
            f"({len(counts):,} raw labels; {collision_count:,} comparison-key variants)"
        )
        values_to_show = counts
        if len(counts) > SHOW_ALL_CATEGORIES_WHEN_AT_MOST:
            values_to_show = counts.head(TOP_CATEGORY_VALUES)
        print_table(
            ("Raw value", "Rows"),
            ((str(value), f"{int(count):,}") for value, count in values_to_show.items()),
        )
        if len(values_to_show) < len(counts):
            print(
                f"Only the {TOP_CATEGORY_VALUES} most frequent values are shown; "
                f"{len(counts) - len(values_to_show):,} less-frequent values are omitted."
            )

    print("\nCase/whitespace variants that would collapse under the comparison key:")
    print_table(
        ("Dataset", "Column", "Comparison key", "Raw variants (rows)"),
        variant_rows or [("none", "none", "none", "none")],
    )


def print_numeric_profile(frames: dict[str, pd.DataFrame]) -> None:
    print_section("5. NUMERIC TYPE CHECKS AND DESCRIPTIVE STATISTICS")
    rows: list[tuple[str, str, str, str, str, str, str, str, str, str, str]] = []
    for dataset, columns in NUMERIC_COLUMNS.items():
        frame = frames[dataset]
        for column in columns:
            values = frame[column]
            present = present_value_mask(values)
            numeric_values = pd.to_numeric(values, errors="coerce")
            invalid = present & numeric_values.isna()
            valid = numeric_values.dropna()
            non_positive = int((valid <= 0).sum())
            rows.append(
                (
                    dataset,
                    column,
                    f"{int(present.sum()):,}",
                    f"{int(values.isna().sum()):,}",
                    f"{int(invalid.sum()):,}",
                    f"{non_positive:,}",
                    format_number(valid.min() if not valid.empty else None),
                    format_number(valid.quantile(0.25) if not valid.empty else None),
                    format_number(valid.median() if not valid.empty else None),
                    format_number(valid.mean() if not valid.empty else None),
                    format_number(valid.max() if not valid.empty else None),
                )
            )
    print_table(
        (
            "Dataset",
            "Column",
            "Present",
            "NULL",
            "Not numeric",
            "<= 0",
            "Min",
            "P25",
            "Median",
            "Mean",
            "Max",
        ),
        rows,
    )
    print("`<= 0` is an observation for review, not an automatic reason to discard a row.")


def print_timestamp_profile(frames: dict[str, pd.DataFrame]) -> None:
    print_section("6. TIMESTAMP TYPE CHECKS AND DATE RANGES")
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for dataset, columns in TIMESTAMP_COLUMNS.items():
        frame = frames[dataset]
        for column in columns:
            values = frame[column]
            present = present_value_mask(values)
            parsed = parse_timestamp(values)
            unparseable = present & parsed.isna()
            valid = parsed.dropna()
            rows.append(
                (
                    dataset,
                    column,
                    f"{int(present.sum()):,}",
                    f"{int(values.isna().sum()):,}",
                    f"{int(unparseable.sum()):,}",
                    valid.min().strftime(TIMESTAMP_FORMAT) if not valid.empty else "-",
                    valid.max().strftime(TIMESTAMP_FORMAT) if not valid.empty else "-",
                )
            )
    print_table(
        ("Dataset", "Column", "Present", "NULL", "Unparseable", "Earliest", "Latest"),
        rows,
    )


def print_domain_checks(frames: dict[str, pd.DataFrame]) -> None:
    print_section("7. DOMAIN CHECKS")
    orders = frames["orders"]
    reviews = frames["reviews"]
    rows: list[tuple[str, str, str, str]] = []

    order_status = comparison_key(orders["order_status"].dropna())
    unexpected_status = sorted(set(order_status.dropna()) - KNOWN_ORDER_STATUSES)
    rows.append(
        (
            "orders.order_status",
            "approved, canceled, created, delivered, invoiced, processing, shipped, unavailable",
            f"{int(order_status.isin(KNOWN_ORDER_STATUSES).sum()):,}",
            ", ".join(unexpected_status) or "none",
        )
    )

    for dataset, column in (("customers", "customer_state"), ("sellers", "seller_state")):
        values = frames[dataset][column].dropna().str.strip().str.upper()
        unexpected_states = sorted(set(values.dropna()) - BRAZILIAN_STATE_CODES)
        rows.append(
            (
                f"{dataset}.{column}",
                "Brazilian two-letter state code",
                f"{int(values.isin(BRAZILIAN_STATE_CODES).sum()):,}",
                ", ".join(unexpected_states) or "none",
            )
        )

    score_values = pd.to_numeric(reviews["review_score"], errors="coerce")
    valid_review_scores = score_values.isin([1, 2, 3, 4, 5])
    review_score_present = present_value_mask(reviews["review_score"])
    invalid_review_scores = review_score_present & ~valid_review_scores
    invalid_score_values = sorted(
        {str(value) for value in reviews.loc[invalid_review_scores, "review_score"]}
    )
    rows.append(
        (
            "reviews.review_score",
            "integer 1 to 5",
            f"{int((review_score_present & valid_review_scores).sum()):,}",
            ", ".join(invalid_score_values) or "none",
        )
    )
    print_table(("Field", "Expected domain", "Valid rows", "Unexpected raw values"), rows)


def count_timestamp_relation(
    left: pd.Series, right: pd.Series, *, left_must_be_before: bool
) -> tuple[int, int]:
    comparable = left.notna() & right.notna()
    if left_must_be_before:
        contradiction = left[comparable] >= right[comparable]
    else:
        contradiction = left[comparable] < right[comparable]
    return int(comparable.sum()), int(contradiction.sum())


def print_temporal_quality(frames: dict[str, pd.DataFrame]) -> None:
    """Report timestamp contradictions without changing source data."""
    print_section("8. TEMPORAL CONSISTENCY AND DELIVERY ELIGIBILITY")
    orders = frames["orders"]
    reviews = frames["reviews"]
    purchase = parse_timestamp(orders["order_purchase_timestamp"])
    approved = parse_timestamp(orders["order_approved_at"])
    carrier = parse_timestamp(orders["order_delivered_carrier_date"])
    delivered = parse_timestamp(orders["order_delivered_customer_date"])
    estimated = parse_timestamp(orders["order_estimated_delivery_date"])
    review_created = parse_timestamp(reviews["review_creation_date"])
    review_answered = parse_timestamp(reviews["review_answer_timestamp"])

    consistency_rows = []
    for label, left, right, left_must_be_before in (
        ("Approval before purchase", approved, purchase, False),
        ("Carrier handoff before purchase", carrier, purchase, False),
        ("Customer delivery before purchase", delivered, purchase, False),
        ("Estimated delivery before purchase", estimated, purchase, False),
        ("Carrier handoff after customer delivery", carrier, delivered, True),
        ("Review answer before review creation", review_answered, review_created, False),
    ):
        comparable, contradictions = count_timestamp_relation(
            left, right, left_must_be_before=left_must_be_before
        )
        consistency_rows.append((label, f"{comparable:,}", f"{contradictions:,}"))
    print_table(("Chronology check", "Comparable rows", "Contradictions"), consistency_rows)

    normalized_status = comparison_key(orders["order_status"])
    is_delivered = normalized_status.eq("delivered").fillna(False)
    has_actual_delivery = delivered.notna()
    has_estimated_delivery = estimated.notna()
    actual_before_purchase = delivered.notna() & purchase.notna() & (delivered < purchase)
    eligible_for_timeliness = (
        is_delivered
        & has_actual_delivery
        & has_estimated_delivery
        & purchase.notna()
        & ~actual_before_purchase
    )
    print("\nDelivery metric:")
    print_table(
        ("Metric", "Orders"),
        (
            ("Delivered orders", f"{int(is_delivered.sum()):,}"),
            (
                "Delivered without a valid actual-delivery timestamp",
                f"{int((is_delivered & ~has_actual_delivery).sum()):,}",
            ),
            (
                "Delivered without a valid estimated-delivery timestamp",
                f"{int((is_delivered & ~has_estimated_delivery).sum()):,}",
            ),
            (
                "Delivered with actual delivery before purchase",
                f"{int((is_delivered & actual_before_purchase).sum()):,}",
            ),
            ("Timeliness-eligible delivered orders", f"{int(eligible_for_timeliness.sum()):,}"),
        ),
    )


def print_review_summary(reviews: pd.DataFrame) -> None:
    reviews_with_order = reviews.dropna(subset=["order_id"])
    reviews_per_order = reviews_with_order.groupby("order_id").size()
    maximum_reviews = int(reviews_per_order.max()) if not reviews_per_order.empty else 0
    reused_id_mask = reviews.duplicated("review_id", keep=False)
    reused_reviews = reviews.loc[reused_id_mask]
    reused_review_ids = reused_reviews["review_id"].nunique()
    reused_ids_across_orders = int(
        (reused_reviews.groupby("review_id")["order_id"].nunique() > 1).sum()
    )
    duplicate_payload_columns = [
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
    ]
    reused_ids_with_identical_payload = sum(
        group[duplicate_payload_columns].drop_duplicates().shape[0] == 1
        for _, group in reused_reviews.groupby("review_id")
    )
    exact_duplicate_rows = int(reviews.duplicated(keep=False).sum())
    orders_with_multiple_review_rows = int((reviews_per_order > 1).sum())

    print_section("9. REVIEW AGGREGATION SHAPE")
    print_table(
        ("Review metric", "Value"),
        (
            ("Review records", f"{len(reviews):,}"),
            ("Distinct source review IDs", f"{reviews['review_id'].nunique():,}"),
            ("Rows with a reused review ID", f"{int(reused_id_mask.sum()):,}"),
            ("Review IDs reused across multiple orders", f"{reused_ids_across_orders:,}"),
            (
                "Reused IDs with one identical payload across those orders",
                f"{reused_ids_with_identical_payload:,}",
            ),
            ("Exactly duplicate full rows", f"{exact_duplicate_rows:,}"),
            ("Orders with at least one review", f"{reviews_per_order.size:,}"),
            ("Orders with multiple review rows", f"{orders_with_multiple_review_rows:,}"),
            ("Maximum reviews for one order", f"{maximum_reviews:,}"),
        ),
    )


def print_category_translation_summary(
    products: pd.DataFrame, translations: pd.DataFrame
) -> None:
    source_categories = products["product_category_name"]
    translated_categories = translations["product_category_name"]
    source_present = present_value_mask(source_categories)
    translation_present = present_value_mask(translated_categories)
    exact_translation_values = set(translated_categories.loc[translation_present])
    exact_missing = source_present & ~source_categories.isin(exact_translation_values)

    source_keys = comparison_key(source_categories)
    translation_keys = set(comparison_key(translated_categories.loc[translation_present]))
    normalised_missing = source_present & ~source_keys.isin(translation_keys)
    unmapped_categories = sorted(source_categories.loc[normalised_missing].dropna().unique())

    print_section("10. CATEGORY-TRANSLATION COVERAGE")
    print_table(
        ("Translation metric", "Value"),
        (
            ("Products with a non-null source category", f"{int(source_present.sum()):,}"),
            (
                "Products without an exact raw translation match",
                f"{int(exact_missing.sum()):,}",
            ),
            (
                "Products still untranslated after case/whitespace comparison",
                f"{int(normalised_missing.sum()):,}",
            ),
            (
                "Untranslated source categories",
                ", ".join(str(category) for category in unmapped_categories) or "none",
            ),
        ),
    )


def main() -> None:
    frames: dict[str, pd.DataFrame] = {}
    missing_files: list[str] = []
    profile_rows: list[tuple[str, str, str, str, str, str]] = []
    null_rows: list[tuple[str, str, str]] = []

    for name, (filename, key_columns) in DATASETS.items():
        file_path = RAW_DATA_DIR / filename
        if not file_path.exists():
            missing_files.append(filename)
            continue

        frame = read_dataset(filename)
        frames[name] = frame
        profile_rows.append(dataset_profile_row(name, frame, key_columns))
        null_rows.extend(nullable_column_rows(name, frame))

    if missing_files:
        raise FileNotFoundError(
            "Missing in-scope source files in data/raw: " + ", ".join(missing_files)
        )

    print("\n" + "=" * 88)
    print("OLIST SOURCE DATA PROFILE")
    print("=" * 88)
    print("Scope: seven warehouse source files in data/raw; the report never edits data.")
    print("Comparison keys reveal label variants only; they are not applied to the CSVs.")

    print_section("1. DATASET INVENTORY")
    print_table(
        (
            "Dataset",
            "Rows",
            "Columns",
            "Candidate key",
            "Missing keys",
            "Duplicate key rows",
        ),
        profile_rows,
    )

    print_section("2. NULL-VALUE SUMMARY")
    print_table(("Dataset", "Column", "NULL rows"), null_rows)

    print_section("3. BLANK OR WHITESPACE-ONLY VALUES")
    print_table(("Dataset", "Column", "Rows"), blank_value_rows(frames))

    print_categorical_profile(frames)
    print_numeric_profile(frames)
    print_timestamp_profile(frames)
    print_domain_checks(frames)

    print_section("REFERENTIAL INTEGRITY")
    foreign_key_rows = (
        missing_reference_row(
            "orders.customer_id -> customers.customer_id",
            frames["orders"],
            "customer_id",
            frames["customers"],
            "customer_id",
        ),
        missing_reference_row(
            "order_items.order_id -> orders.order_id",
            frames["order_items"],
            "order_id",
            frames["orders"],
            "order_id",
        ),
        missing_reference_row(
            "order_items.product_id -> products.product_id",
            frames["order_items"],
            "product_id",
            frames["products"],
            "product_id",
        ),
        missing_reference_row(
            "order_items.seller_id -> sellers.seller_id",
            frames["order_items"],
            "seller_id",
            frames["sellers"],
            "seller_id",
        ),
        missing_reference_row(
            "reviews.order_id -> orders.order_id",
            frames["reviews"],
            "order_id",
            frames["orders"],
            "order_id",
        ),
        missing_reference_row(
            "products.category -> category_translation.category",
            frames["products"],
            "product_category_name",
            frames["category_translation"],
            "product_category_name",
        ),
    )
    print_table(("Child reference", "Missing parents", "Rows checked"), foreign_key_rows)

    print_temporal_quality(frames)
    print_review_summary(frames["reviews"])
    print_category_translation_summary(
        frames["products"], frames["category_translation"]
    )


if __name__ == "__main__":
    main()
