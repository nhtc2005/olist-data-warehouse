# Report evidence snapshot

Generated on 2026-11-01 from the current local PostgreSQL database, model metadata and a fresh execution of all notebook code cells. This is supporting evidence, not the course report.

## Verification

- Staging: 31 checks passed; warehouse: 17; feature mart: 6.
- Python syntax passed. All notebook code cells executed in a fresh namespace and reproduced current model metrics without publishing artifacts.
- All three Streamlit pages passed AppTest; capacities 0/1/10/100%, an empty sales period, a small zero-late state, and mismatched metadata were checked.
- The historical-outcome table matches the ranked monitoring list and its predicted-risk percentages.
- Per-order item counts and total values reconcile between the feature mart and warehouse.

## Physical tables

| Schema | Table | Rows | Columns |
| --- | --- | ---: | ---: |
| dw | `dim_customer` | 99,441 | 7 |
| dw | `dim_date` | 800 | 10 |
| dw | `dim_product` | 32,951 | 14 |
| dw | `dim_seller` | 3,095 | 6 |
| dw | `fact_delivery` | 99,441 | 17 |
| dw | `fact_sales` | 112,650 | 9 |
| mart | `order_delivery_ml_features` | 99,441 | 12 |
| mart | `order_late_risk` | 28,935 | 7 |
| staging | `stg_category_translation` | 71 | 2 |
| staging | `stg_customers` | 99,441 | 5 |
| staging | `stg_order_items` | 112,650 | 7 |
| staging | `stg_orders` | 99,441 | 8 |
| staging | `stg_products` | 32,951 | 9 |
| staging | `stg_reviews` | 99,224 | 7 |
| staging | `stg_sellers` | 3,095 | 4 |

The DW has six physical tables (four dimensions and two facts), with 63 columns in total. Staging has seven tables; the feature/scoring mart has two.

Schema update on 2026-11-03: the redundant constant quantity column was removed from the DW creation/load code. Column counts above describe the revised schema after the next pipeline rebuild, which has not been run as part of this edit. Row counts and numerical results remain the measured 2026-11-01 snapshot. Each sales row still represents one item unit, counted using `COUNT(*)`.

## Dashboard sales and delivery measures

- Sales purchase-date filter bounds: 2016-09-04 to 2018-09-03.
- Non-canceled item revenue: **R$ 13,496,408.43**; distinct orders with item lines: **98,205**; AOV: **R$ 137.43**.
- Warehouse item revenue across all statuses: R$ 13,591,643.70; freight across all statuses: R$ 2,251,909.54.
- Excluded canceled orders with item lines: 461; excluded item value: R$ 95,235.27.
- All order records: 99,441; timeliness-eligible delivered orders: 96,470; late orders: 6,534; late rate: 6.77%; temporal-anomaly flags: 189.
- Revenue excludes freight and canceled orders only; other statuses remain. AOV uses the same sales population. Late rate has a different denominator. ML order value includes freight.
- Category revenue per order uses only category item revenue, not full-basket revenue; order counts overlap across categories.

## Top revenue groups

| Category | Non-canceled revenue | Orders containing category |
| --- | ---: | ---: |
| health_beauty | R$ 1,255,695.13 | 8,800 |
| watches_gifts | R$ 1,198,185.21 | 5,604 |
| bed_bath_table | R$ 1,035,964.06 | 9,399 |
| sports_leisure | R$ 979,740.92 | 7,673 |
| computers_accessories | R$ 904,322.02 | 6,654 |
| furniture_decor | R$ 727,465.05 | 6,425 |
| housewares | R$ 626,825.80 | 5,847 |
| cool_stuff | R$ 620,835.39 | 3,617 |
| auto | R$ 586,620.73 | 3,873 |
| garden_tools | R$ 481,009.94 | 3,505 |

| Customer state | Non-canceled revenue | Orders |
| --- | ---: | ---: |
| SP | R$ 5,165,166.12 | 41,128 |
| RJ | R$ 1,811,923.32 | 12,698 |
| MG | R$ 1,573,667.19 | 11,497 |
| RS | R$ 742,809.68 | 5,416 |
| PR | R$ 676,883.06 | 4,982 |
| SC | R$ 518,578.28 | 3,599 |
| BA | R$ 507,108.83 | 3,344 |
| DF | R$ 300,886.45 | 2,120 |
| GO | R$ 287,870.46 | 1,998 |
| ES | R$ 273,532.13 | 2,018 |

## Model population and results

Scores created at: `2026-11-01T12:57:33.987371+00:00`. Six model features; Logistic Regression only.

| Split | Start purchase day | End purchase day | Orders | Late orders | Late rate |
| --- | --- | --- | ---: | ---: | ---: |
| train | 2016-09-15 | 2018-04-15 | 67,515 | 5,287 | 7.83% |
| validation | 2018-04-15 | 2018-06-21 | 14,467 | 627 | 4.33% |
| test | 2018-06-21 | 2018-08-29 | 14,468 | 618 | 4.27% |

Boundary days overlap because row counts determine the chronological splits. Training-label availability at a deployment cutoff is not simulated.

| Split | Average precision (PR-AUC) | ROC-AUC | Brier | Recall at top 10% |
| --- | ---: | ---: | ---: | ---: |
| validation | 0.109386 | 0.720324 | 0.040277 | 31.90% |
| test | 0.075400 | 0.643101 | 0.040652 | 17.96% |

Fixed validation-derived alert threshold: **0.071428**. This is separate from the dashboard capacity policy.

| Split | Fixed-threshold flagged orders | Precision | Recall |
| --- | ---: | ---: | ---: |
| validation | 1,447 | 13.82% | 31.90% |
| test | 1,848 | 7.20% | 21.52% |

## Test-only review-capacity scenarios

| Capacity | Reviewed | Late captured | Reviewed but on time | Precision | Late coverage | Random expected captures | Lift |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0% | 0 | 0 | 0 | — | 0.00% | 0.00 | — |
| 5% | 723 | 69 | 654 | 9.54% | 11.17% | 30.88 | 2.23 |
| 10% | 1,446 | 111 | 1,335 | 7.68% | 17.96% | 61.77 | 1.80 |
| 20% | 2,893 | 172 | 2,721 | 5.95% | 27.83% | 123.57 | 1.39 |
| 50% | 7,234 | 458 | 6,776 | 6.33% | 74.11% | 309.00 | 1.48 |
| 100% | 14,468 | 618 | 13,850 | 4.27% | 100.00% | 618.00 | 1.00 |

Captured historical late orders are not delays prevented. The monitoring list is a retrospective test-cohort simulation, not a live queue or day-by-day replay.

## Platform checks

- `docker compose ps --format {{.Service}} {{.State}} {{.Health}}` returned exit code 0.
```text
airflow-apiserver running healthy
airflow-dag-processor running healthy
airflow-db running healthy
airflow-scheduler running healthy
db running healthy
```
- `docker compose exec -T airflow-scheduler airflow dags list-import-errors --output json` returned exit code 0.
```text
[]
```

## Evidence still to prepare for submission

- Capture current screenshots of all three pages and successful Airflow runs. Functional AppTest is not browser/pixel-level visual QA.
- Include the DW relationship diagram, ETL flow and DSS decision workflow in the report.
- Cold-start deployment and a complete DAG rerun were not performed by this read-only audit. No ETL runtime or before/after performance benchmark was measured.
- Explain statistical findings using modeling.md and source_data_profile.md; detailed notebook tables can be placed in an appendix.
- Do not invent intervention savings, causal delay explanations, deployment success on an untested machine or individual contribution percentages.
