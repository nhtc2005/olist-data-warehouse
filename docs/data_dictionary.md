# Data dictionary and layer contracts

For dataset context, scope, entity relationships, profile results, and known limitations, see [source_data_profile.md](source_data_profile.md). For feature selection, model evaluation, and scoring decisions, see [modeling.md](modeling.md). This document defines the data contract from the raw CSV files through `staging`, the `dw` star schema, the ML feature mart, and the model-scoring output.

## Scope and staging rules

This dictionary covers the seven in-scope Olist source files. The raw `payment` and `geolocation` files remain in `data/raw/` but are outside this project's first version and are not loaded into PostgreSQL.

The `staging` schema is a raw landing area, not the data warehouse. Every source field is loaded as `TEXT` so the CSV values remain traceable and malformed values can be inspected instead of blocking the load. Empty unquoted CSV values are represented as `NULL`; no rows are removed, deduplicated, translated, aggregated, trimmed, or assigned surrogate keys in staging. Type conversion and business cleaning occur only when dimensions and facts are loaded.

## Source-to-staging mapping

The `DW target type` column shows the typed downstream use of a field. When a source field is not persisted in the star schema, it states the field's use there or `Not loaded` instead.

### `olist_orders_dataset.csv` -> `staging.stg_orders`

**Grain:** one order. **Candidate key:** `order_id`.

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `order_id` | identifier | `TEXT` | `TEXT` | Order business identifier. |
| `customer_id` | identifier | `TEXT` | `TEXT` | Source customer/address identifier for the order. |
| `order_status` | category | `TEXT` | `TEXT` | Lifecycle status, such as `delivered`, `canceled`, or `shipped`. |
| `order_purchase_timestamp` | `YYYY-MM-DD HH:MI:SS` | `TEXT` | `TIMESTAMP` | Customer purchase time. |
| `order_approved_at` | timestamp; nullable | `TEXT` | `TIMESTAMP` | Payment/order approval time. |
| `order_delivered_carrier_date` | timestamp; nullable | `TEXT` | `TIMESTAMP` | Time handed to carrier. |
| `order_delivered_customer_date` | timestamp; nullable | `TEXT` | `TIMESTAMP` | Actual delivery time to customer. |
| `order_estimated_delivery_date` | timestamp | `TEXT` | `TIMESTAMP` | Promised delivery time. |

### `olist_customers_dataset.csv` -> `staging.stg_customers`

**Grain:** one `customer_id` shipping-address record. **Candidate key:** `customer_id`. `customer_unique_id` identifies the underlying customer across orders.

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `customer_id` | identifier | `TEXT` | `TEXT` | Source customer/address key used by `orders`. |
| `customer_unique_id` | identifier | `TEXT` | `TEXT` | Stable customer identifier across purchase records. |
| `customer_zip_code_prefix` | ZIP prefix; preserve leading zeroes | `TEXT` | `TEXT` | Customer postal-code prefix. |
| `customer_city` | text | `TEXT` | `TEXT` | Customer city as supplied. |
| `customer_state` | two-letter state code | `TEXT` | `TEXT` | Customer state. |

### `olist_order_items_dataset.csv` -> `staging.stg_order_items`

**Grain:** one item line in an order. **Candidate key:** (`order_id`, `order_item_id`).

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `order_id` | identifier | `TEXT` | `TEXT` | Parent order identifier. |
| `order_item_id` | positive integer | `TEXT` | `INTEGER` | Item-line sequence within an order. |
| `product_id` | identifier | `TEXT` | `TEXT` | Product sold on the line. |
| `seller_id` | identifier | `TEXT` | `TEXT` | Seller fulfilling the item line. |
| `shipping_limit_date` | timestamp | `TEXT` | `TIMESTAMP` | Seller shipping deadline. |
| `price` | decimal currency amount | `TEXT` | `NUMERIC(14,2)` | Product revenue for the item line, excluding freight. |
| `freight_value` | decimal currency amount | `TEXT` | `NUMERIC(14,2)` | Freight charge for the item line. |

### `olist_products_dataset.csv` -> `staging.stg_products`

**Grain:** one product. **Candidate key:** `product_id`.

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `product_id` | identifier | `TEXT` | `TEXT` | Product business identifier. |
| `product_category_name` | Portuguese category; nullable | `TEXT` | `TEXT` | Source product category. |
| `product_name_lenght` | integer; source spelling retained | `TEXT` | `INTEGER` | Product-name character count. |
| `product_description_lenght` | integer; source spelling retained | `TEXT` | `INTEGER` | Product-description character count. |
| `product_photos_qty` | integer | `TEXT` | `INTEGER` | Number of product photos. |
| `product_weight_g` | integer grams; nullable | `TEXT` | `INTEGER` | Product weight in grams. |
| `product_length_cm` | decimal/integer centimetres; nullable | `TEXT` | `NUMERIC(10,2)` | Product length in centimetres. |
| `product_height_cm` | decimal/integer centimetres; nullable | `TEXT` | `NUMERIC(10,2)` | Product height in centimetres. |
| `product_width_cm` | decimal/integer centimetres; nullable | `TEXT` | `NUMERIC(10,2)` | Product width in centimetres. |

### `olist_sellers_dataset.csv` -> `staging.stg_sellers`

**Grain:** one seller. **Candidate key:** `seller_id`.

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `seller_id` | identifier | `TEXT` | `TEXT` | Seller business identifier. |
| `seller_zip_code_prefix` | ZIP prefix; preserve leading zeroes | `TEXT` | `TEXT` | Seller postal-code prefix. |
| `seller_city` | text | `TEXT` | `TEXT` | Seller city as supplied. |
| `seller_state` | two-letter state code | `TEXT` | `TEXT` | Seller state. |

### `olist_order_reviews_dataset.csv` -> `staging.stg_reviews`

**Grain:** one source review submission. `review_id` is not globally unique in this source, and an order can have multiple reviews. Staging retains all rows. When loading the order-level fact, the DW removes duplicate pairs of (`order_id`, `review_id`) only, then aggregates the remaining rows by `order_id`.

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `review_id` | identifier | `TEXT` | Deduplication key | Source review identifier. |
| `order_id` | identifier | `TEXT` | `TEXT` | Order reviewed. |
| `review_score` | integer 1-5 | `TEXT` | `NUMERIC(3,2)` aggregate | Customer rating. |
| `review_comment_title` | free text; nullable | `TEXT` | Not loaded | Review title; outside current NLP scope. |
| `review_comment_message` | free text; nullable | `TEXT` | Not loaded | Review message; outside current NLP scope. |
| `review_creation_date` | timestamp | `TEXT` | Deduplication ordering | Review creation time. |
| `review_answer_timestamp` | timestamp; nullable | `TEXT` | Deduplication ordering | Seller/platform response time. |

### `product_category_name_translation.csv` -> `staging.stg_category_translation`

**Grain:** one source category. **Candidate key:** `product_category_name`.

| Column | Source format | Staging type | DW target type | Meaning |
| --- | --- | --- | --- | --- |
| `product_category_name` | Portuguese category text | `TEXT` | `TEXT` | Source category used to join products. |
| `product_category_name_english` | English text | `TEXT` | `TEXT` | English category label. |

## Staging validation, not cleaning

After loading, validate row counts, candidate-key duplicates, source nulls, and the source relationships below. Report issues; do not alter the staging records to make a check pass.

- `stg_orders.customer_id` -> `stg_customers.customer_id`
- `stg_order_items.order_id` -> `stg_orders.order_id`
- `stg_order_items.product_id` -> `stg_products.product_id`
- `stg_order_items.seller_id` -> `stg_sellers.seller_id`
- `stg_reviews.order_id` -> `stg_orders.order_id`
- `stg_products.product_category_name` -> `stg_category_translation.product_category_name` when the category is not null

## DW transformation rules

- The DW load first validates the staging contract, then drops and recreates the whole `dw` schema in one transaction. A failed transformation rolls the transaction back; it does not leave a partially refreshed DW.
- `dim_date` covers each day from the earliest purchase date through the latest estimated-delivery date. It serves purchase, approval, actual-delivery, and estimated-delivery roles.
- `dim_customer`, `dim_product`, and `dim_seller` retain source business identifiers and receive surrogate integer keys.
- `fact_sales` has one row per (`order_id`, `order_item_id`). `item_revenue` comes from `price`, `freight_value` stays separate, and `quantity` is always 1 because a source item row represents one unit. `shipping_limit_timestamp` retains the seller deadline for that item.
- `fact_delivery` has one row per `order_id`. Before review aggregation, the load keeps one row per (`order_id`, `review_id`), preferring the latest `review_answer_timestamp` and then the latest `review_creation_date`. A reused `review_id` on different orders is retained for every associated order. The remaining rows are aggregated into `review_avg_score` and `review_record_count`.
- A delivery KPI is eligible only when the order is `delivered`, purchase, actual-delivery, and estimated-delivery timestamps are present, and actual delivery is not before purchase. For ineligible orders, `is_late` and `delivery_delay_days` are `NULL`, never zero.
- If a product category is missing or has no translation, `category_name_en` is `Unknown / untranslated`; the raw Portuguese category remains available. Zero or negative product dimensions/weight become analytical `NULL` and are flagged with `has_physical_anomaly`.
- Source timestamps are never corrected. `has_temporal_anomaly` is `TRUE` when approval or carrier handoff precedes purchase, carrier handoff follows actual delivery, actual delivery precedes purchase, or the estimate precedes purchase. A late delivery by itself is not a temporal anomaly.

## DW physical model

`dw` is the cleaned star schema. There is no separate persisted `clean` schema.

| Table | Grain | Primary key | Purpose |
| --- | --- | --- | --- |
| `dw.dim_date` | One calendar day | `date_key` | Shared date attributes for order events. |
| `dw.dim_customer` | One source `customer_id` | `customer_key` | Customer/address identity and geography. |
| `dw.dim_seller` | One source `seller_id` | `seller_key` | Seller identity and geography. |
| `dw.dim_product` | One source `product_id` | `product_key` | Product category, attributes, and quality flags. |
| `dw.fact_sales` | One (`order_id`, `order_item_id`) | (`order_id`, `order_item_id`) | Item-level sales and fulfilment deadline. |
| `dw.fact_delivery` | One order | `order_id` | Order lifecycle, delivery outcome, and review aggregate. |

### `dw.dim_date`

| Column | Type | Constraints | Meaning |
| --- | --- | --- | --- |
| `date_key` | `INTEGER` | Primary key | Date encoded as `YYYYMMDD`. |
| `calendar_date` | `DATE` | `NOT NULL`, unique | Calendar date. |
| `calendar_year` | `SMALLINT` | `NOT NULL` | Calendar year. |
| `calendar_quarter` | `SMALLINT` | `NOT NULL`, 1-4 | Calendar quarter. |
| `calendar_month` | `SMALLINT` | `NOT NULL`, 1-12 | Calendar month. |
| `calendar_day` | `SMALLINT` | `NOT NULL`, 1-31 | Day of month. |
| `iso_weekday` | `SMALLINT` | `NOT NULL`, 1-7 | ISO weekday: Monday is 1 and Sunday is 7. |
| `month_name` | `TEXT` | `NOT NULL` | Month name generated by PostgreSQL. |
| `day_name` | `TEXT` | `NOT NULL` | Day name generated by PostgreSQL. |
| `is_weekend` | `BOOLEAN` | `NOT NULL` | `TRUE` for ISO Saturday or Sunday. |

### `dw.dim_customer`

| Column | Type | Constraints | Meaning |
| --- | --- | --- | --- |
| `customer_key` | `BIGINT` | Generated identity, primary key | DW surrogate key. |
| `customer_id` | `TEXT` | `NOT NULL`, unique | Source shipping-address identifier. |
| `customer_unique_id` | `TEXT` | `NOT NULL` | Identifier shared by the same customer across orders. |
| `zip_code_prefix` | `TEXT` | `NOT NULL` | Postal-code prefix, kept as text to preserve leading zeroes. |
| `city_raw` | `TEXT` | `NOT NULL` | City exactly as supplied in the source. |
| `city_normalized` | `TEXT` | `NOT NULL` | Lower-case city with outer and repeated whitespace normalised. |
| `state_code` | `CHAR(2)` | `NOT NULL`, valid Brazilian state code | Upper-case state code. |

### `dw.dim_seller`

| Column | Type | Constraints | Meaning |
| --- | --- | --- | --- |
| `seller_key` | `BIGINT` | Generated identity, primary key | DW surrogate key. |
| `seller_id` | `TEXT` | `NOT NULL`, unique | Source seller identifier. |
| `zip_code_prefix` | `TEXT` | `NOT NULL` | Seller postal-code prefix, kept as text to preserve leading zeroes. |
| `city_raw` | `TEXT` | `NOT NULL` | City exactly as supplied in the source. |
| `city_normalized` | `TEXT` | `NOT NULL` | Lower-case city with outer and repeated whitespace normalised. |
| `state_code` | `CHAR(2)` | `NOT NULL`, valid Brazilian state code | Upper-case state code. |

`city_normalized` trims outer whitespace, collapses repeated internal whitespace, and converts to lower case. It does not infer spelling, accent, or city-synonym mappings.

### `dw.dim_product`

| Column | Type | Constraints | Meaning |
| --- | --- | --- | --- |
| `product_key` | `BIGINT` | Generated identity, primary key | DW surrogate key. |
| `product_id` | `TEXT` | `NOT NULL`, unique | Source product identifier. |
| `category_name_raw` | `TEXT` | Nullable | Portuguese category after converting blank values to `NULL`. |
| `category_name_normalized` | `TEXT` | Nullable | Lower-case category with surrounding and repeated whitespace normalised. |
| `category_name_en` | `TEXT` | `NOT NULL` | English translation, or `Unknown / untranslated`. |
| `product_name_length` | `INTEGER` | Nullable | Source product-name length. |
| `product_description_length` | `INTEGER` | Nullable | Source product-description length. |
| `product_photos_qty` | `INTEGER` | Nullable | Number of product photos. |
| `weight_g` | `INTEGER` | Nullable; positive when present | Product weight in grams. |
| `length_cm` | `NUMERIC(10,2)` | Nullable; positive when present | Product length in centimetres. |
| `height_cm` | `NUMERIC(10,2)` | Nullable; positive when present | Product height in centimetres. |
| `width_cm` | `NUMERIC(10,2)` | Nullable; positive when present | Product width in centimetres. |
| `has_missing_category` | `BOOLEAN` | `NOT NULL` | `TRUE` when the source category is missing. |
| `has_physical_anomaly` | `BOOLEAN` | `NOT NULL` | `TRUE` when a supplied physical measurement is zero or negative. |

### `dw.fact_sales`

| Column | Type | Constraints | Meaning |
| --- | --- | --- | --- |
| `order_id` | `TEXT` | `NOT NULL`, composite primary key | Source order identifier. |
| `order_item_id` | `INTEGER` | `NOT NULL`, positive, composite primary key | Item-line sequence within the order. |
| `customer_key` | `BIGINT` | `NOT NULL`, FK to `dim_customer` | Customer/address for the order. |
| `product_key` | `BIGINT` | `NOT NULL`, FK to `dim_product` | Product on the item line. |
| `seller_key` | `BIGINT` | `NOT NULL`, FK to `dim_seller` | Seller fulfilling the item line. |
| `purchase_date_key` | `INTEGER` | `NOT NULL`, FK to `dim_date` | Purchase calendar day. |
| `shipping_limit_timestamp` | `TIMESTAMP` | `NOT NULL` | Seller shipping deadline for the item line. |
| `item_revenue` | `NUMERIC(14,2)` | `NOT NULL`, non-negative | Item `price`, excluding freight. |
| `freight_value` | `NUMERIC(14,2)` | `NOT NULL`, non-negative | Freight charge for the item line. |
| `quantity` | `SMALLINT` | `NOT NULL`, default and constrained to 1 | One source item row represents one unit. |

`shipping_limit_timestamp` is retained because it is useful for analysing seller fulfilment deadlines and deriving later DSS features.

### `dw.fact_delivery`

| Column | Type | Constraints | Meaning |
| --- | --- | --- | --- |
| `order_id` | `TEXT` | Primary key | Source order identifier. |
| `customer_key` | `BIGINT` | `NOT NULL`, FK to `dim_customer` | Customer/address for the order. |
| `order_status` | `TEXT` | `NOT NULL`, valid normalised source status | Lower-case lifecycle status. |
| `purchase_date_key` | `INTEGER` | `NOT NULL`, FK to `dim_date` | Purchase calendar day. |
| `approval_date_key` | `INTEGER` | Nullable, FK to `dim_date` | Approval calendar day. |
| `actual_delivery_date_key` | `INTEGER` | Nullable, FK to `dim_date` | Actual delivery calendar day. |
| `estimated_delivery_date_key` | `INTEGER` | `NOT NULL`, FK to `dim_date` | Promised delivery calendar day. |
| `purchase_timestamp` | `TIMESTAMP` | `NOT NULL` | Purchase time. |
| `approved_timestamp` | `TIMESTAMP` | Nullable | Approval time. |
| `actual_delivery_timestamp` | `TIMESTAMP` | Nullable | Actual delivery time. |
| `estimated_delivery_timestamp` | `TIMESTAMP` | `NOT NULL` | Promised delivery time. |
| `is_timeliness_eligible` | `BOOLEAN` | `NOT NULL` | Has the valid delivery information required to calculate lateness. |
| `is_late` | `BOOLEAN` | Nullable; required when timeliness-eligible | `TRUE` when actual delivery is after the estimate. |
| `delivery_delay_days` | `NUMERIC(10,2)` | Nullable; required when timeliness-eligible | Actual minus estimated delivery time in days. |
| `has_temporal_anomaly` | `BOOLEAN` | `NOT NULL` | Flags contradictory source event ordering. |
| `review_avg_score` | `NUMERIC(3,2)` | Nullable; 1-5 when present | Mean review score after per-order review aggregation. |
| `review_record_count` | `SMALLINT` | `NOT NULL`, default 0, non-negative | Review rows after per-order duplicate-pair handling. |

The four date-key columns connect the order to its purchase, approval, actual-delivery, and estimated-delivery days. The table constraint requires both `is_late` and `delivery_delay_days` to be populated exactly when `is_timeliness_eligible = TRUE`; otherwise they are both `NULL`. `has_temporal_anomaly` is independent of the late-delivery label.

## ML feature mart

`mart.order_delivery_ml_features` is rebuilt by `olist_ml_features_pipeline` after the DW validation succeeds. Its grain is one row per `order_id`.

| Column | Type | Constraints | Role and meaning |
| --- | --- | --- | --- |
| `order_id` | `TEXT` | Primary key | Identifier: order business identifier. |
| `purchase_date_key` | `INTEGER` | `NOT NULL` | Time split: purchase day key for chronological splitting. |
| `purchase_month` | `SMALLINT` | `NOT NULL`, 1-12 | Feature: calendar month of purchase. |
| `purchase_weekday` | `SMALLINT` | `NOT NULL`, 1-7 | Feature: ISO weekday; Monday is 1 and Sunday is 7. |
| `promised_lead_time_days` | `NUMERIC(10,2)` | Nullable | Feature: days from approval to estimated delivery; `NULL` when this interval is not valid. |
| `customer_state` | `CHAR(2)` | `NOT NULL` | Feature: standardised customer state. |
| `has_out_of_state_seller` | `BOOLEAN` | Nullable | Feature: whether at least one seller is in a different state from the customer. It is `NULL` for orders with no item lines. |
| `item_count` | `INTEGER` | `NOT NULL`, non-negative | Feature: number of item lines on the order. |
| `total_order_value` | `NUMERIC(14,2)` | `NOT NULL`, non-negative | Feature: sum of item revenue and freight. |
| `is_ml_eligible` | `BOOLEAN` | `NOT NULL` | Eligibility: has approval time, non-negative promised lead time, and at least one item. |
| `is_timeliness_eligible` | `BOOLEAN` | `NOT NULL` | Historical-label eligibility: has sufficient valid delivery information to determine lateness. |
| `is_late` | `BOOLEAN` | Nullable; required when timeliness-eligible | Target: `TRUE` when actual delivery was later than estimated delivery. |

The training population is the intersection of `is_ml_eligible = TRUE` and `is_timeliness_eligible = TRUE`. Actual delivery time, delivery delay, final order status, carrier events, reviews, and review-derived fields are intentionally absent to prevent outcome leakage.

## Model scoring output

`src/ml/train_model.py` fits the selected Logistic Regression model on the earliest 70% of eligible labelled orders, selects its alert threshold from the following 15%, and scores both validation and test orders. It overwrites the current fitted pipeline and metadata under `models/`, then refreshes `mart.order_late_risk` for the dashboard.

### `mart.order_late_risk`

This table is rebuilt each time the training script runs. It contains the current model output only; the metrics and split dates for that same run are in `models/late_delivery_metadata.json`.

| Column | Type | Constraints | Role and meaning |
| --- | --- | --- | --- |
| `order_id` | `TEXT` | Primary key | Order receiving the risk score. |
| `purchase_date_key` | `INTEGER` | `NOT NULL` | Purchase date key retained for dashboard filtering. |
| `population` | `TEXT` | `validation`, `test`, or `production` | Population in which the order was scored. The script writes validation and test scores. |
| `risk_probability` | `DOUBLE PRECISION` | `NOT NULL`, 0-1 | Predicted probability that the order will be late. |
| `alert_threshold` | `DOUBLE PRECISION` | `NOT NULL`, 0-1 | Run-specific cutoff selected from validation scores. |
| `risk_band` | `TEXT` | `high` or `routine` | `high` when `risk_probability >= alert_threshold`; otherwise `routine`. |
| `scored_at` | `TIMESTAMPTZ` | `NOT NULL` | UTC time at which the score was created. |
