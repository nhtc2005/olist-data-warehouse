# Late-delivery modeling

## Objective

The DSS estimates the risk that an eligible order will be delivered on a calendar date after its estimated delivery date. Delivery at any time on the estimated date is on time. It is a prioritisation aid: a high-risk score identifies an order worth checking, not a certain late delivery.

## Data and features

The model reads one row per order from `mart.order_delivery_ml_features`. The labelled population requires both `is_ml_eligible = TRUE` and `is_timeliness_eligible = TRUE`.

Logistic Regression uses six pre-delivery features:

- `promised_lead_time_days`
- `item_count`
- `total_order_value`
- `purchase_month`
- `customer_state`
- `has_out_of_state_seller`

`purchase_weekday` remains in the feature mart for analysis but is not passed to the model. Its association with the calendar-date label is negligible (Cramer's V about 0.017), despite a statistically significant chi-square result.

Actual delivery timestamps, delay, final order status, carrier events, and reviews are excluded because they are only known after the delivery outcome.

## Checks before training

The notebook checks missing values, reports IQR outliers, and does not delete valid extreme orders. Numeric inputs are median-imputed and robust-scaled; categorical inputs use most-frequent imputation and one-hot encoding.

The executed notebook reports the following training-period results using calendar-date labels.

Mann-Whitney U tests show statistically detectable differences for all three numeric features, although the practical differences are small. The late-order median is higher for order value and slightly lower for promised lead time; both groups have a median item count of one.

| Numeric feature | Late-order median | On-time-order median | Mann-Whitney p-value |
| --- | ---: | ---: | ---: |
| `total_order_value` | 115.88 | 103.065 | 9.83e-23 |
| `item_count` | 1 | 1 | 7.94e-7 |
| `promised_lead_time_days` | 23.02 | 23.38 | 1.45e-4 |

| Categorical feature | Cramer's V | Decision |
| --- | ---: | --- |
| `purchase_month` | about 0.166 | Keep |
| `customer_state` | about 0.161 | Keep; interpret the chi-square test cautiously because the minimum expected count is about 2.27, below five |
| `has_out_of_state_seller` | about 0.090 | Keep |
| `purchase_weekday` | about 0.017 | Exclude from the model |

## Training and evaluation

Eligible labelled orders are sorted by purchase date and `order_id`, then split chronologically:

- earliest 70%: training
- next 15%: validation
- latest 15%: test

Logistic Regression fits the training period only, using `max_iter=1000` and `random_state=42`.

Evaluation records average precision (labelled PR-AUC), ROC-AUC, Brier score, and recall among the top 10% of orders by risk. Capacity is rounded down to whole orders; the training script breaks equal-score ties by order ID. Day boundaries can overlap between splits because the split uses row counts rather than entire calendar days.

The validation period chooses the alert threshold at the 90th percentile of predicted probabilities. Orders at or above that fixed threshold are labelled `high` risk. The model is then evaluated on the test period; the number of test alerts may differ from 10% because the threshold stays fixed.

The latest alert threshold and validation/test metrics are recorded in `models/late_delivery_metadata.json`.

The run on 2026-11-01 produced the following results using calendar-date labels:

| Split | PR-AUC | ROC-AUC | Brier score | Recall in top 10% |
| --- | ---: | ---: | ---: | ---: |
| Validation | 0.1094 | 0.7203 | 0.0403 | 31.90% |
| Test | 0.0754 | 0.6431 | 0.0407 | 17.96% |

The alert threshold is `0.0714`.

At the fixed threshold, 1,848 of 14,468 test orders were flagged, with 7.20% precision and 21.52% recall. The model provides modest risk prioritisation.

## Outputs

Running `src/ml/train_model.py` overwrites the current model and metadata:

- `models/late_delivery_model.joblib`
- `models/late_delivery_metadata.json`

It also refreshes `mart.order_late_risk`. The table stores validation and test scores, their predicted probabilities, the selected threshold, and the `high` or `routine` risk band. The dashboard uses test scores only and selects its monitoring list by capacity rather than the fixed alert threshold.

## Review-capacity scenario

The Delivery risk simulation page uses the test population exclusively. Training fits the model; validation selects the alert threshold; neither population is selectable on the dashboard. A 0–100% review-capacity slider defaults to 10%. A customer-state filter defines the cohort, which is ranked by saved probability descending and order ID ascending. The review budget is `floor(cohort size × capacity / 100)`.

The **Orders to monitor** table is a retrospective simulation of the orders a team would prioritise using pre-delivery features. Its title intentionally omits the word “simulated”. It does not represent live outstanding shipments or a day-by-day replay of historical shipment status. For reports, describe it as a capacity-based historical test-cohort simulation. Promised delivery dates provide context; actual outcomes are excluded from the monitoring table and its CSV export.

The table and all scenario calculations use the same top-N list. The preview displays at most 500 rows; CSV download includes the entire selected list. Numeric columns remain numeric for sorting. Order value includes freight, unlike sales revenue. The proposed workflow is to verify seller/carrier progress and the delivery commitment, then consider customer communication after verification; no individual cause of delay is inferred from a risk score.

The Historical outcomes for the monitoring list expander shows each order ID, its original predicted late-delivery risk as a percentage, and its actual historical outcome. It uses the same ranked selection and 500-row preview limit. The risk estimate is not a certainty or a per-order accuracy score.

Historical evaluation shows orders reviewed, actual late orders captured, coverage of all late orders, and reviewed orders delivered on time. Precision is captured late orders / reviewed orders; recall equals coverage. F1 is `2 × captured late orders / (reviewed orders + all late orders)`. Ratios with zero denominators display as `—`. These technical ratios and global test metrics appear under Model evaluation details. Global test metrics do not change with state or capacity filters.

Random-selection expected captures equal `reviewed orders × cohort late rate`; lift equals precision / cohort late rate. The coverage curve compares top-N ranking with the expected random baseline at each floor-rounded budget. This is an expectation, not an intervention experiment or an estimate of delays prevented. Small cohorts below 100 orders receive a caution; cohorts without late orders have undefined coverage/lift. This scenario does not change the saved alert threshold.

## Score freshness and publication

A successful staging reload, DW rebuild, or feature-mart rebuild drops `mart.order_late_risk` inside the same transaction. A failed rebuild rolls back this invalidation. Always run the three data pipelines in order and rerun training/scoring after any upstream rebuild. The separate manual DAGs do not enforce this order automatically; do not run refresh and training concurrently.

Training commits scores before publishing model/metadata files through temporary-file replacement. Publication across PostgreSQL and the filesystem is not a single atomic transaction. On every dashboard interaction, one repeatable-read database snapshot checks population row counts, scoring timestamps and thresholds against metadata, and checks the test join count before showing a list. Missing or mismatched scores stop the page with recovery instructions instead of serving cached results. This protects the supported pipeline path; manual edits to source tables outside these pipelines require an explicit rebuild and retraining.

## Limitations

The project deliberately uses a single Logistic Regression model to keep the decision-support workflow interpretable and reproducible. It is a modest risk-ranking aid, not an automatic delivery decision system. A small predicted probability is not the model's accuracy: only 618 of 14,468 test orders were late (4.27%). At 10% review capacity, the model ranks 111 late orders into a list of 1,446 orders, giving 7.68% precision and 17.96% coverage. Random selection of the same size would capture approximately 61.77 late orders on average, so the observed lift is approximately 1.80. These results establish historical ranking value, not proven operational benefit.

| Limitation | Evidence or practical consequence | Proposed improvement |
| --- | --- | --- |
| Modest detection at limited capacity | The top 10% captures only 111 of 618 test late orders; 507 remain outside the monitoring list. Many reviewed orders are actually on time. | Evaluate several review capacities and choose one using review cost and the benefit of identifying a late order. Keep human verification rather than automatic interventions. |
| Limited early-order information | Six pre-delivery features describe orders and broad geography, but do not describe execution of the shipment. This is a plausible constraint, not proof of the sole cause of limited performance. | First assess additional features available at the same prediction point, such as product weight/volume, seller geography, seller count and geographical distance where reliable source coverage permits. Fit transformations and select features using training/validation only. |
| Coarse geography | A different-state seller flag does not measure distance, route or transport difficulty. | Consider customer–seller distance or region combinations after validating geographic mappings; define aggregation for orders with multiple sellers. |
| Restricted model form | The current additive logistic specification does not explicitly include nonlinear numeric effects or interactions. | If validation evidence justifies it, test a small number of interpretable transformations or interactions within Logistic Regression. Do not assume that adding complexity will improve results. |
| Performance changes across periods | Validation average precision is 0.1094 and top-10% recall is 31.90%, versus 0.0754 and 17.96% on test. This indicates period-dependent performance, not a confirmed diagnosis of its cause. | Use rolling chronological validation windows to assess stability. Monitor late-rate, ranking and calibration changes when new data becomes available. |
| Rare target and uncertain probability calibration | The test late rate is 4.27%; low probabilities or high majority-class accuracy alone cannot establish model quality. Brier score alone is not a full calibration diagnosis. | Report average precision, recall/precision at a fixed capacity, lift and an appropriate baseline. Inspect calibration by risk bins before presenting probabilities as reliable absolute risks. |
| Retrospective split and outcome availability | Splits use purchase-day row order, allowing boundary days to overlap. Labels for some late training purchases may not yet have been known at a real deployment cutoff. | Split at whole-day boundaries and require training labels to have matured before each evaluation cutoff. Preserve chronological ordering and avoid repeated tuning on the already-inspected test set. |
| Selected historical population | Training/evaluation require eligible orders with known delivered outcomes; this does not represent all open, canceled or unresolved orders in production. | Define the intended scoring population and obtain follow-up outcomes for prospectively scored orders before claiming production generalisation. |
| No live feed or measured intervention effect | The dataset is a static historical sample. Captured late orders are not delays prevented; neither causal explanations nor financial savings have been demonstrated. | If a live source becomes available, define ingestion/scoring schedules and evaluate review actions prospectively. Introduce retraining when fresh data and monitoring evidence justify it. |

For the course report, describe the model as providing **modest but measurable prioritisation above a random-selection baseline under a fixed review budget**. Do not claim high predictive accuracy, calibrated probabilities, causal drivers of delay, or prevented delays without supporting evaluation. The current scope retains one model; the improvement directions above are proposals, not implemented capabilities.
