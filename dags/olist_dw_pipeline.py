"""Olist warehouse DAG."""

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

from etl.transform_and_load_dw import transform_and_load_dw
from etl.validate_dw import validate_dw


@dag(
    dag_id="olist_dw_pipeline",
    description="Standardise validated staging data, rebuild the Olist DW, and reconcile it.",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["olist", "warehouse", "etl"],
)
def olist_dw_pipeline():
    @task(task_id="transform_and_load_dw")
    def transform_and_load_dw_task() -> dict[str, int]:
        return transform_and_load_dw()

    @task(task_id="validate_dw")
    def validate_dw_task() -> dict[str, int]:
        return validate_dw()

    transform = transform_and_load_dw_task()
    validation = validate_dw_task()
    transform >> validation


olist_dw_pipeline()
