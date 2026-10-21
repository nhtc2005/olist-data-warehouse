"""Olist ML feature-mart DAG."""

from __future__ import annotations

import sys
from pathlib import Path

import pendulum
from airflow.sdk import dag, task


CONTAINER_SOURCE_DIR = Path("/opt/airflow/project/src")
LOCAL_SOURCE_DIR = Path(__file__).resolve().parents[1] / "src"
SOURCE_DIR = CONTAINER_SOURCE_DIR if CONTAINER_SOURCE_DIR.exists() else LOCAL_SOURCE_DIR

if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from ml.build_features import build_ml_features
from ml.validate_features import validate_ml_features


@dag(
    dag_id="olist_ml_features_pipeline",
    description="Build and validate the Olist order-level ML feature mart.",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["olist", "mart", "ml", "etl"],
)
def olist_ml_features_pipeline():
    @task(task_id="build_ml_features")
    def build_ml_features_task() -> dict[str, int]:
        return build_ml_features()

    @task(task_id="validate_ml_features")
    def validate_ml_features_task() -> dict[str, int]:
        return validate_ml_features()

    build = build_ml_features_task()
    validate = validate_ml_features_task()
    build >> validate


olist_ml_features_pipeline()
