# Source-data description and profiling

## Dataset context

This project uses the [Olist Brazilian E-Commerce Public Dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce), a public relational snapshot of a Brazilian marketplace. It describes orders placed from 2016 to 2018, together with the customers, sellers, products, delivery events, and customer reviews associated with them.

The source is historical and static: it is suitable for reproducing ETL, OLAP, and late-delivery-risk experiments, but it is not a live operational feed. Timestamps are supplied without an explicit time-zone offset, so the project must not make claims that depend on a specific time zone. Monetary fields are treated as Brazilian real (R$), as documented by the dataset provider.

Raw files remain unchanged under `data/raw/`. This document records the project scope, grain, profile results, data-quality findings, and the agreed direction for cleaning. Field definitions and the source-to-staging contract are in [data_dictionary.md](data_dictionary.md).

## Project scope

The first warehouse iteration includes the following seven files.

| Source file | Rows profiled | Grain | Candidate key | Project use |
| --- | ---: | --- | --- | --- |
| `olist_orders_dataset.csv` | 99,441 | One order | `order_id` | Order lifecycle and delivery timestamps. |
| `olist_customers_dataset.csv` | 99,441 | One customer shipping-address record | `customer_id` | Customer geography and repeat-customer identifier. |
| `olist_order_items_dataset.csv` | 112,650 | One item line in one order | (`order_id`, `order_item_id`) | Revenue, freight, product, and seller links. |
| `olist_products_dataset.csv` | 32,951 | One product | `product_id` | Category and physical product attributes. |
| `olist_sellers_dataset.csv` | 3,095 | One seller | `seller_id` | Seller geography. |
| `olist_order_reviews_dataset.csv` | 99,224 | One source review record associated with an order | Not unique: `review_id` is reused | Customer-satisfaction measure. |
| `product_category_name_translation.csv` | 71 | One Portuguese-category translation | `product_category_name` | English category labels for presentation. |

Two raw files are deliberately excluded from the first version:

| Excluded file | Reason |
| --- | --- |
| `olist_order_payments_dataset.csv` | Payment-method analysis is outside the agreed business questions. |
| `olist_geolocation_dataset.csv` | Fine-grained distance calculation and route optimisation are outside scope; state-level geography is sufficient for the initial DSS. |

## Business entities and relationships

```text
customers  1 ──< orders  1 ──< order_items >── 1 products
                         |          |
                         |          └──────────> 1 sellers
                         └──< reviews

products ──> category_translation
```

- `customer_id` identifies the shipping-address record for an order. `customer_unique_id` identifies the underlying customer across orders; the two identifiers must not be treated as interchangeable.
- An order can contain multiple item lines and can involve multiple sellers.
- An order can have multiple review rows. Review records must therefore be aggregated to `order_id` before joining them to order-level delivery data.
- Product categories are supplied in Portuguese; the translation table is a presentation aid, not a replacement for the original category value.

## Reproducible profiling method

Run the profiler from the project root:

```powershell
python src/etl/profile_source.py
```

The profiler reads CSV values as strings so IDs and ZIP prefixes cannot lose leading zeroes. It is read-only: it neither updates a raw file nor changes staging data. The report checks:

- file availability, row/column counts, candidate-key completeness, duplicate candidate keys, `NULL`s, and blank/whitespace-only strings;
- categorical label frequencies, cardinality, surrounding/repeated whitespace, and labels that would collapse under a case-insensitive comparison key;
- domain validity for order status, Brazilian state codes, and review score;
- numeric parseability and descriptive statistics; timestamp parseability, date range, and event chronology;
- referential integrity, delivery eligibility, review multiplicity/reused IDs, and category-translation coverage.

The script prints every status, state, and category value because these domains are small. For cities, it prints cardinality and the 20 most frequent values because there are thousands of distinct values. This document records the findings needed for the warehouse design; the complete distribution remains reproducible from the source files and script.

## Structural and referential-integrity results

| Dataset | Missing candidate-key rows | Duplicate candidate-key rows | Result |
| --- | ---: | ---: | --- |
| Orders | 0 | 0 | `order_id` is suitable as the order business key. |
| Customers | 0 | 0 | `customer_id` is suitable as the shipping-address key. |
| Order items | 0 | 0 | (`order_id`, `order_item_id`) is suitable as the item-line key. |
| Products | 0 | 0 | `product_id` is suitable as the product key. |
| Sellers | 0 | 0 | `seller_id` is suitable as the seller key. |
| Reviews | 0 | 1,603 | `review_id` is not a unique fact key. |
| Category translations | 0 | 0 | `product_category_name` is suitable as the mapping key. |

All five entity references resolve successfully:

| Child reference | Missing parent references |
| --- | ---: |
| `orders.customer_id` → `customers.customer_id` | 0 of 99,441 |
| `order_items.order_id` → `orders.order_id` | 0 of 112,650 |
| `order_items.product_id` → `products.product_id` | 0 of 112,650 |
| `order_items.seller_id` → `sellers.seller_id` | 0 of 112,650 |
| `reviews.order_id` → `orders.order_id` | 0 of 99,224 |

The category translation is not a mandatory entity reference. It has 13 unmatched non-null product rows, detailed in section 6.

## Labels, domains, and text quality

### Categorical domains

| Field | Raw distinct values | Comparison-key values | Profile result |
| --- | ---: | ---: | --- |
| `orders.order_status` | 8 | 8 | All 99,441 rows are within the expected Olist status domain. |
| `customers.customer_state` | 27 | 27 | All rows use valid Brazilian two-letter state codes. |
| `sellers.seller_state` | 23 | 23 | All rows use valid Brazilian two-letter state codes; the source simply has sellers in 23 states. |
| `customers.customer_city` | 4,119 | 4,119 | No case/whitespace variants detected. |
| `sellers.seller_city` | 611 | 608 | Three comparison-key variants caused by repeated internal spaces. |
| `products.product_category_name` | 73 | 73 | No case/whitespace variants detected; 610 product rows are null. |
| Translation source category | 71 | 71 | No case/whitespace variants detected. |
| Translation English category | 71 | 71 | No case/whitespace variants detected. |

The order-status distribution is:

| Status | Orders |
| --- | ---: |
| `delivered` | 96,478 |
| `shipped` | 1,107 |
| `canceled` | 625 |
| `unavailable` | 609 |
| `invoiced` | 314 |
| `processing` | 301 |
| `created` | 5 |
| `approved` | 2 |

The three seller-city comparison-key variants are caused solely by double spaces:

| Normalised comparison value | Raw variants |
| --- | --- |
| `ferraz de vasconcelos` | `ferraz de vasconcelos`; `ferraz de  vasconcelos` |
| `sao jose dos pinhais` | `sao jose dos pinhais`; `sao  jose dos pinhais` |
| `sao paulo` | `sao paulo`; `sao  paulo` |

The DW should retain the supplied city value in a raw column and create a normalised analytical value by trimming and reducing repeated spaces. It must not infer city synonym, spelling, or accent mappings without a maintained reference mapping.

### Missing categories and translation coverage

- 610 product rows have no source category and related descriptive product attributes are also null.
- 32,341 products have a non-null source category. Of those, 13 have no exact English translation; case/whitespace comparison does not resolve any additional match.
- The untranslated source categories are `pc_gamer` and `portateis_cozinha_e_preparadores_de_alimentos`.

The warehouse retains the Portuguese category. Missing or untranslated English labels are presented as `Unknown / untranslated`; no synonym is invented.

### Blank free text

There are no blank/whitespace-only values in keys, labels, numeric, or timestamp fields. The review text fields contain 2 whitespace-only titles and 27 whitespace-only messages. They should be represented as `NULL` if those fields are ever loaded to a detailed review table. They are outside the current NLP scope.

## Numeric checks and descriptive statistics

All populated numeric candidate values parse successfully. The table below describes valid parsed values; `<= 0` is a finding to review, not a reason to silently remove a row.

| Dataset | Field | NULL | Non-numeric | <= 0 | Min | P25 | Median | Mean | Max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Order items | `order_item_id` | 0 | 0 | 0 | 1 | 1 | 1 | 1.20 | 21 |
| Order items | `price` | 0 | 0 | 0 | 0.85 | 39.90 | 74.99 | 120.65 | 6,735 |
| Order items | `freight_value` | 0 | 0 | 383 | 0 | 13.08 | 16.26 | 19.99 | 409.68 |
| Products | `product_name_lenght` | 610 | 0 | 0 | 5 | 42 | 51 | 48.48 | 76 |
| Products | `product_description_lenght` | 610 | 0 | 0 | 4 | 339 | 595 | 771.50 | 3,992 |
| Products | `product_photos_qty` | 610 | 0 | 0 | 1 | 1 | 1 | 2.19 | 20 |
| Products | `product_weight_g` | 2 | 0 | 4 | 0 | 300 | 700 | 2,276.47 | 40,425 |
| Products | `product_length_cm` | 2 | 0 | 0 | 7 | 18 | 25 | 30.82 | 105 |
| Products | `product_height_cm` | 2 | 0 | 0 | 2 | 8 | 13 | 16.94 | 105 |
| Products | `product_width_cm` | 2 | 0 | 0 | 6 | 15 | 20 | 23.20 | 118 |
| Reviews | `review_score` | 0 | 0 | 0 | 1 | 4 | 5 | 4.09 | 5 |

Zero freight appears on 383 item lines and can represent free shipping, so it remains zero. Four products have `product_weight_g = 0`; this is a suspicious physical attribute. The raw value remains traceable and the DW can expose an anomaly flag or analytical `NULL` rather than treating it as a real zero-weight item.

## Timestamp checks, ranges, and chronology

All populated timestamp values parse exactly in the documented `YYYY-MM-DD HH:MI:SS` format.

| Dataset | Timestamp field | NULL | Unparseable | Earliest valid value | Latest valid value |
| --- | --- | ---: | ---: | --- | --- |
| Orders | `order_purchase_timestamp` | 0 | 0 | 2016-09-04 21:15:19 | 2018-10-17 17:30:18 |
| Orders | `order_approved_at` | 160 | 0 | 2016-09-15 12:16:38 | 2018-09-03 17:40:06 |
| Orders | `order_delivered_carrier_date` | 1,783 | 0 | 2016-10-08 10:34:01 | 2018-09-11 19:48:28 |
| Orders | `order_delivered_customer_date` | 2,965 | 0 | 2016-10-11 13:46:32 | 2018-10-17 13:22:46 |
| Orders | `order_estimated_delivery_date` | 0 | 0 | 2016-09-30 00:00:00 | 2018-11-12 00:00:00 |
| Order items | `shipping_limit_date` | 0 | 0 | 2016-09-19 00:15:34 | 2020-04-09 22:35:08 |
| Reviews | `review_creation_date` | 0 | 0 | 2016-10-02 00:00:00 | 2018-08-31 00:00:00 |
| Reviews | `review_answer_timestamp` | 0 | 0 | 2016-10-07 18:32:28 | 2018-10-29 12:27:35 |

Chronology checks identify the following anomalies:

| Chronology condition checked | Comparable rows | Contradictions |
| --- | ---: | ---: |
| Approval earlier than purchase | 99,281 | 0 |
| Carrier handoff earlier than purchase | 97,658 | 166 |
| Customer delivery earlier than purchase | 96,476 | 0 |
| Estimated delivery earlier than purchase | 99,441 | 0 |
| Carrier handoff later than customer delivery | 96,475 | 32 |
| Review answer earlier than review creation | 99,224 | 0 |

The 166 early carrier handoffs and 32 carrier-after-delivery records are source timing contradictions. They must never be rewritten in staging. In the DW, invalid carrier timing is omitted from carrier-based analytical roles and `has_temporal_anomaly` is set to `TRUE`.

### Delivery eligibility

| Metric | Orders |
| --- | ---: |
| Delivered orders | 96,478 |
| Delivered without a valid actual-delivery timestamp | 8 |
| Delivered without a valid estimated-delivery timestamp | 0 |
| Delivered with actual delivery before purchase | 0 |
| Timeliness-eligible delivered orders | 96,470 |

A timeliness-eligible order must have status `delivered`, a valid purchase timestamp, valid actual and estimated delivery timestamps, and an actual delivery not earlier than purchase. Ineligible orders remain in the warehouse; delivery measures are `NULL`, not zero.

## Review quality and aggregation policy

The profile separates two different review multiplicity conditions:

| Review metric | Value |
| --- | ---: |
| Source review rows | 99,224 |
| Distinct source `review_id` values | 98,410 |
| Rows with a reused `review_id` | 1,603 |
| `review_id` values reused across multiple orders | 789 |
| Reused IDs with one identical payload across those orders | 789 |
| Exactly duplicate full rows | 0 |
| Orders with at least one review row | 98,673 |
| Orders with multiple review rows | 547 |
| Maximum review rows for one order | 3 |

The 789 reused review IDs have identical score, text, creation time, and answer time but are attached to different orders. This is a source-level identifier reuse, not an exact duplicate row. Conversely, the 547 multi-review orders are the one-to-many order-to-review relationship and are not automatically errors.

Rules for the warehouse are:

- Staging retains every raw review row.
- Do not deduplicate globally by `review_id`, because that would remove a review association from one or more orders without a defensible selection rule.
- Aggregate all review rows by `order_id` into `review_avg_score` and `review_record_count` for `fact_delivery`.
- Store a quality indicator such as `has_reused_review_id` or `reused_review_row_count` so the affected orders can be identified.
- If a future extract contains an exact full-row duplicate or an identical (`order_id`, `review_id`) duplicate, keep the raw rows in staging but retain one deterministic copy for order-level aggregation and log the excluded duplicate count.

Reviews are outcome information. They support satisfaction KPIs and DSS analysis after fulfilment, but cannot be model features for prediction made at or shortly after order confirmation.

## Definitions used by the warehouse and DSS

- **Revenue:** `SUM(order_items.price)`. Freight is reported separately and is not product revenue.
- **Late delivery:** a timeliness-eligible order whose actual delivery timestamp is later than its estimated delivery timestamp. A negative delay means early delivery, not an error.
- **Review score at order level:** arithmetic mean of valid review scores, with `review_record_count` retained beside the mean. A low-review order has an average score of 2 or below.
- **Initial DSS geography:** customer state. City-level results are optional only after state-level results are checked for adequate sample size.
- **Label standardisation:** order status is trimmed and stored in lower case; state is trimmed and stored in upper case; cities are trimmed with repeated spaces reduced, while the raw city remains available for traceability. IDs and ZIP prefixes remain text and are never case-normalised.
- **No invented repair:** source nulls are not imputed in ETL; numeric, domain, and key errors stop a load for investigation. Observed timing contradictions and suspicious physical values are flagged rather than silently rewritten.
- **ML prediction point:** after an order is confirmed and its estimated delivery timestamp is available. Features observed after this point, including actual delivery, delay, review, and final status, must not be used to predict late delivery.

## Limitations and responsible use

- The data represents a historical marketplace sample, not the current performance of Olist or any other platform.
- The project can describe patterns and rank risk; it cannot establish that a seller, area, or product characteristic causes a delay or a low review.
- State is a coarse geographic proxy. Without using the excluded geolocation file, the project does not calculate physical delivery distance.
- Customer and seller identifiers are pseudonymous. They are used only for joins and aggregation, never for attempts to identify people or businesses.
- The profiler detects exact label variation from whitespace/case. It intentionally does not infer that differently spelled, accented, synonymous, or geographically ambiguous city names should be merged.
- Source changes must be detected through file/header checks and a fresh profile before staging reload; a successful past profile does not guarantee a future extract has the same structure or quality.
