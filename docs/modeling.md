# Late-delivery modeling

## Objective

The DSS estimates the risk that an eligible order will be delivered after its estimated delivery date. It is a prioritisation aid: a high-risk score identifies an order worth checking, not a certain late delivery.

## Data and features

The model reads one row per order from `mart.order_delivery_ml_features`. The labelled population requires both `is_ml_eligible = TRUE` and `is_timeliness_eligible = TRUE`.

The final Logistic Regression uses six pre-delivery features:

- `promised_lead_time_days`
- `item_count`
- `total_order_value`
- `purchase_month`
- `customer_state`
- `has_out_of_state_seller`

`purchase_weekday` remains in the feature mart for analysis but is not passed to the model. Its association with the label was negligible (Cramer's V about 0.021).

Actual delivery timestamps, delay, final order status, carrier events, and reviews are excluded because they are only known after the delivery outcome.

## Checks before training

The notebook checks missing values, reports IQR outliers, and does not delete valid extreme orders. Numeric inputs are median-imputed and robust-scaled; categorical inputs use most-frequent imputation and one-hot encoding.

Mann-Whitney U tests on the training period showed statistically detectable differences for all three numeric features, although the practical differences were small. The late-order median was higher for order value and slightly lower for promised lead time; both groups had a median item count of one.

| Categorical feature | Cramer's V | Decision |
| --- | ---: | --- |
| `purchase_month` | about 0.173 | Keep |
| `customer_state` | about 0.161 | Keep; interpret the chi-square test cautiously because some expected counts are below five |
| `has_out_of_state_seller` | about 0.088 | Keep |
| `purchase_weekday` | about 0.021 | Exclude from the model |

## Training and evaluation

Eligible labelled orders are sorted by purchase date and `order_id`, then split chronologically:

- earliest 70%: training
- next 15%: validation
- latest 15%: test

The validation period chooses the alert threshold at the 90th percentile of predicted probabilities. The resulting threshold is `0.0857`; validation orders at or above that value are labelled `high` risk.

| Split | PR-AUC | ROC-AUC | Brier score |
| --- | ---: | ---: | ---: |
| Validation | 0.1318 | 0.7209 | 0.0491 |
| Test | 0.1132 | 0.6626 | 0.0610 |

The test metrics are lower than validation metrics, which is expected for the later time period. Logistic Regression is the only deployed model; the notebook is kept focused on this selected model rather than a multi-model search.

## Outputs

Running `src/ml/train_model.py` overwrites the current model and metadata:

- `models/late_delivery_model.joblib`
- `models/late_delivery_metadata.json`

It also refreshes `mart.order_late_risk`. The table stores validation and test scores, their predicted probabilities, the selected threshold, and the `high` or `routine` risk band used by the dashboard.

## Limitations

The dataset is historical and has no live production population. Individual predictors have modest effects, so the model should support prioritisation rather than automatic delivery decisions. Retraining or production scoring should only be introduced when new orders arrive on a defined schedule.
