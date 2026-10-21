"""Train and score the late-delivery model."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, RobustScaler

try:
    from etl.load_staging import connect_to_warehouse
except ModuleNotFoundError:
    SOURCE_DIR = Path(__file__).resolve().parents[1]
    if str(SOURCE_DIR) not in sys.path:
        sys.path.insert(0, str(SOURCE_DIR))
    from etl.load_staging import connect_to_warehouse


ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "models"
MODEL_PATH = MODELS_DIR / "late_delivery_model.joblib"
METADATA_PATH = MODELS_DIR / "late_delivery_metadata.json"
NUMERIC_FEATURES = (
    "promised_lead_time_days",
    "item_count",
    "total_order_value",
)
MODEL_CATEGORICAL_FEATURES = (
    "purchase_month",
    "customer_state",
    "has_out_of_state_seller",
)
MODEL_FEATURES = (*NUMERIC_FEATURES, *MODEL_CATEGORICAL_FEATURES)
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15
ALERT_FRACTION = 0.10

FEATURE_QUERY = """
SELECT
    order_id,
    purchase_date_key,
    purchase_month,
    customer_state,
    has_out_of_state_seller,
    promised_lead_time_days,
    item_count,
    total_order_value,
    is_ml_eligible,
    is_timeliness_eligible,
    is_late
FROM mart.order_delivery_ml_features
ORDER BY purchase_date_key, order_id
"""

DDL_STATEMENTS: tuple[str, ...] = (
    "DROP TABLE IF EXISTS mart.order_late_risk",
    """
    CREATE TABLE mart.order_late_risk (
        order_id TEXT PRIMARY KEY,
        purchase_date_key INTEGER NOT NULL,
        population TEXT NOT NULL CHECK (population IN ('validation', 'test', 'production')),
        risk_probability DOUBLE PRECISION NOT NULL CHECK (risk_probability BETWEEN 0 AND 1),
        alert_threshold DOUBLE PRECISION NOT NULL CHECK (alert_threshold BETWEEN 0 AND 1),
        risk_band TEXT NOT NULL CHECK (risk_band IN ('high', 'routine')),
        scored_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX idx_order_late_risk_population
    ON mart.order_late_risk(population)
    """,
    """
    CREATE INDEX idx_order_late_risk_probability
    ON mart.order_late_risk(risk_probability DESC)
    """,
)


def load_features() -> pd.DataFrame:
    """Read and prepare eligible labelled orders."""
    with connect_to_warehouse() as connection:
        features = pd.read_sql_query(FEATURE_QUERY, connection)

    features["purchase_date"] = pd.to_datetime(
        features["purchase_date_key"].astype(str), format="%Y%m%d", errors="raise"
    )
    for column in NUMERIC_FEATURES:
        features[column] = pd.to_numeric(features[column], errors="coerce")
    for column in ("is_ml_eligible", "is_timeliness_eligible", "is_late"):
        features[column] = features[column].astype("boolean")
    features["has_out_of_state_seller"] = features["has_out_of_state_seller"].map(
        {True: "yes", False: "no"}
    ).astype(object)

    labelled = features.loc[
        features["is_ml_eligible"]
        & features["is_timeliness_eligible"]
        & features["is_late"].notna()
    ].copy()
    if labelled.empty:
        raise ValueError("No eligible labelled rows. Run the ML feature-mart pipeline first.")
    return labelled.sort_values(["purchase_date", "order_id"]).reset_index(drop=True)


def split_features(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split orders into chronological train, validation, and test periods."""
    train_end = int(len(features) * TRAIN_FRACTION)
    validation_end = int(len(features) * (TRAIN_FRACTION + VALIDATION_FRACTION))
    train = features.iloc[:train_end].copy()
    validation = features.iloc[train_end:validation_end].copy()
    test = features.iloc[validation_end:].copy()

    for name, frame in (("train", train), ("validation", validation), ("test", test)):
        if frame.empty or frame["is_late"].nunique() != 2:
            raise ValueError(f"The {name} split needs orders from both target classes.")
    return train, validation, test


def build_pipeline() -> Pipeline:
    """Build the selected logistic-regression pipeline."""
    preprocessor = ColumnTransformer(
        [
            (
                "numeric",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", RobustScaler()),
                    ]
                ),
                list(NUMERIC_FEATURES),
            ),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("one_hot", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                list(MODEL_CATEGORICAL_FEATURES),
            ),
        ]
    )
    return Pipeline(
        [
            ("preprocessor", preprocessor),
            ("model", LogisticRegression(max_iter=1_000, random_state=42)),
        ]
    )


def evaluate_probabilities(
    labels: pd.Series, probabilities: np.ndarray, threshold: float | None = None
) -> dict[str, float | int]:
    """Calculate ranking and calibration metrics."""
    top_count = max(1, int(np.ceil(len(probabilities) * ALERT_FRACTION)))
    top_indices = np.argsort(probabilities)[-top_count:]
    metrics: dict[str, float | int] = {
        "pr_auc": float(average_precision_score(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
        "brier_score": float(brier_score_loss(labels, probabilities)),
        "recall_at_top_10_pct": float(labels.iloc[top_indices].sum() / labels.sum()),
    }
    if threshold is not None:
        flagged = probabilities >= threshold
        metrics["flagged_orders"] = int(flagged.sum())
        metrics["precision_at_threshold"] = float(labels[flagged].mean()) if flagged.any() else 0.0
        metrics["recall_at_threshold"] = float(labels[flagged].sum() / labels.sum())
    return metrics


def _period_details(frame: pd.DataFrame) -> dict[str, str | int]:
    return {
        "start_date": frame["purchase_date"].min().date().isoformat(),
        "end_date": frame["purchase_date"].max().date().isoformat(),
        "orders": int(len(frame)),
    }


def _write_artifacts(
    pipeline: Pipeline,
    metadata: dict[str, object],
) -> tuple[Path, Path]:
    MODELS_DIR.mkdir(exist_ok=True)
    joblib.dump(pipeline, MODEL_PATH)
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return MODEL_PATH, METADATA_PATH


def _risk_rows(
    frame: pd.DataFrame,
    probabilities: np.ndarray,
    population: str,
    threshold: float,
    scored_at: datetime,
) -> list[tuple[object, ...]]:
    return [
        (
            row.order_id,
            int(row.purchase_date_key),
            population,
            float(probability),
            threshold,
            "high" if probability >= threshold else "routine",
            scored_at,
        )
        for row, probability in zip(frame.itertuples(index=False), probabilities, strict=True)
    ]


def _persist_scores(
    validation: pd.DataFrame,
    test: pd.DataFrame,
    threshold: float,
    validation_probabilities: np.ndarray,
    test_probabilities: np.ndarray,
    scored_at: datetime,
) -> None:
    with connect_to_warehouse() as connection:
        with connection.cursor() as cursor:
            for statement in DDL_STATEMENTS:
                cursor.execute(statement)
            cursor.executemany(
                """
                INSERT INTO mart.order_late_risk (
                    order_id, purchase_date_key, population,
                    risk_probability, alert_threshold, risk_band, scored_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                _risk_rows(
                    validation,
                    validation_probabilities,
                    "validation",
                    threshold,
                    scored_at,
                )
                + _risk_rows(
                    test,
                    test_probabilities,
                    "test",
                    threshold,
                    scored_at,
                ),
            )


def train_and_score() -> dict[str, object]:
    """Train the selected model, evaluate it, and save holdout scores."""
    features = load_features()
    train, validation, test = split_features(features)
    pipeline = build_pipeline()

    train_labels = train["is_late"].astype(int)
    validation_labels = validation["is_late"].astype(int)
    test_labels = test["is_late"].astype(int)
    pipeline.fit(train[list(MODEL_FEATURES)], train_labels)

    validation_probabilities = pipeline.predict_proba(validation[list(MODEL_FEATURES)])[:, 1]
    threshold = float(np.quantile(validation_probabilities, 1 - ALERT_FRACTION))
    test_probabilities = pipeline.predict_proba(test[list(MODEL_FEATURES)])[:, 1]
    validation_metrics = evaluate_probabilities(
        validation_labels, validation_probabilities, threshold
    )
    test_metrics = evaluate_probabilities(test_labels, test_probabilities, threshold)

    scored_at = datetime.now(UTC)
    metadata: dict[str, object] = {
        "algorithm": "logistic_regression",
        "feature_version": "order_delivery_features_v1",
        "features": list(MODEL_FEATURES),
        "alert_fraction": ALERT_FRACTION,
        "alert_threshold": threshold,
        "splits": {
            "train": _period_details(train),
            "validation": _period_details(validation),
            "test": _period_details(test),
        },
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "created_at": scored_at.isoformat(),
    }
    model_path, metadata_path = _write_artifacts(pipeline, metadata)
    _persist_scores(
        validation,
        test,
        threshold,
        validation_probabilities,
        test_probabilities,
        scored_at,
    )

    return {
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "alert_threshold": threshold,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "scored_orders": len(validation) + len(test),
    }


def main() -> None:
    result = train_and_score()
    print(f"Saved model: {result['model_path']}")
    print(f"Saved metadata: {result['metadata_path']}")
    print(f"Alert threshold: {result['alert_threshold']:.4f}")
    print(f"Validation PR-AUC: {result['validation_metrics']['pr_auc']:.4f}")
    print(f"Test PR-AUC: {result['test_metrics']['pr_auc']:.4f}")
    print(f"Scored orders: {result['scored_orders']:,}")


if __name__ == "__main__":
    main()
