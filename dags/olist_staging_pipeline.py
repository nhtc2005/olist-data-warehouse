"""Olist staging DAG."""

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

from etl.load_staging import load_staging
from etl.profile_source import main as profile_source
from etl.validate_staging import validate_staging


@dag(
    dag_id="olist_staging_pipeline",
    description="Profile Olist CSVs, then atomically reload and validate PostgreSQL staging.",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["olist", "staging", "etl"],
)
def olist_staging_pipeline():
    @task(task_id="profile_source")
    def profile_source_task() -> None:
        profile_source()

    @task(task_id="load_staging")
    def load_staging_task() -> dict[str, int]:
        return load_staging()

    @task(task_id="validate_staging")
    def validate_staging_task() -> dict[str, int]:
        return validate_staging()

    profile = profile_source_task()
    staging = load_staging_task()
    validation = validate_staging_task()
    profile >> staging >> validation


olist_staging_pipeline()
