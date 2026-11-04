# Warehouse and DSS diagrams

These diagrams describe the current implementation. Render the Mermaid blocks or redraw them for the report; do not present conceptual connections to the mart as physical foreign-key constraints.

## System and ETL flow

```mermaid
flowchart LR
    CSV[Seven raw CSV files] --> PROFILE[Source profiling]
    PROFILE --> STG[Reload staging and validate]
    STG --> DW[Rebuild dimensional warehouse and validate]
    DW --> FEATURES[Build feature mart and validate]
    FEATURES --> LR[Local Logistic Regression training and scoring]
    LR --> SCORES[Saved model, metadata and holdout scores]
    DW --> SALES[Overview and Sales analysis]
    SCORES --> DSS[Test-only delivery risk simulation]
```

The three Airflow DAGs run manually in sequence. Training/scoring is a separate local command. A successful upstream rebuild invalidates saved scores; the operator must complete downstream rebuilds and scoring before using the risk page again.

## Dimensional warehouse

```mermaid
erDiagram
    DIM_CUSTOMER ||--o{ FACT_SALES : customer_key
    DIM_PRODUCT ||--o{ FACT_SALES : product_key
    DIM_SELLER ||--o{ FACT_SALES : seller_key
    DIM_DATE ||--o{ FACT_SALES : purchase_date_key
    DIM_CUSTOMER ||--o{ FACT_DELIVERY : customer_key
    DIM_DATE ||--o{ FACT_DELIVERY : purchase_date_key
    DIM_DATE ||--o{ FACT_DELIVERY : estimated_delivery_date_key
    DIM_DATE o|--o{ FACT_DELIVERY : approval_date_key
    DIM_DATE o|--o{ FACT_DELIVERY : actual_delivery_date_key

    DIM_CUSTOMER {
        bigint customer_key PK
        text customer_id UK
        text customer_unique_id
        char state_code
    }
    DIM_PRODUCT {
        bigint product_key PK
        text product_id UK
        text category_name_en
    }
    DIM_SELLER {
        bigint seller_key PK
        text seller_id UK
        char state_code
    }
    DIM_DATE {
        integer date_key PK
        date calendar_date UK
        smallint calendar_year
        smallint calendar_month
    }
    FACT_SALES {
        text order_id PK
        integer order_item_id PK
        bigint customer_key FK
        bigint product_key FK
        bigint seller_key FK
        integer purchase_date_key FK
        numeric item_revenue
        numeric freight_value
    }
    FACT_DELIVERY {
        text order_id PK
        bigint customer_key FK
        integer purchase_date_key FK
        integer approval_date_key FK
        integer actual_delivery_date_key FK
        integer estimated_delivery_date_key FK
        boolean is_timeliness_eligible
        boolean is_late
        numeric delivery_delay_days
        numeric review_avg_score
    }
```

This diagram shows selected fields; the complete 63-column physical contract is in data_dictionary.md. Four dimensions and two facts form a shared-dimension fact constellation. Each fact has a star-shaped relationship to its dimensions. The date table plays four roles for delivery; approval and actual-delivery foreign keys are nullable. Each sales row represents one item unit; unit counts use `COUNT(*)` without a stored quantity column.

fact_sales has one row per (order_id, order_item_id); fact_delivery has one row per order. Do not join the two facts and sum order-level values without respecting their different grains. Aggregate item data to order grain first for the ML mart. Reviews are deduplicated per (order_id, review_id), then aggregated by order before being attached to fact_delivery.

## Decision workflow

```mermaid
flowchart TD
    A[Understand historical sales and delivery performance] --> B[Select customer state in the test cohort]
    B --> C[Choose review capacity]
    C --> D[Rank saved pre-delivery risk scores]
    D --> E[Select floor-rounded top-N orders]
    E --> F[Orders to monitor and CSV export]
    E --> G[Evaluate against known historical outcomes]
    G --> H[Compare coverage with expected random selection]
    H --> C
    F --> I[Human verifies fulfilment progress and delivery commitment]
```

The final human action is a proposed operational workflow, not a measured intervention performed by this project. The model ranks orders without using outcomes; actual outcomes are only used for retrospective evaluation. One model is managed through its pipeline, artifact, metadata, evaluation and scoring lifecycle; there is no multi-model registry.
