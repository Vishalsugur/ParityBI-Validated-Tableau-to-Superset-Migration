"""
Service Desk BI pipeline
========================

Loads the public ServiceNow incident event log (UCI, CC BY 4.0) into PostgreSQL,
builds a star schema, checks data quality, publishes extracts for the legacy
Tableau dashboard and proves the new Superset dashboards show the same KPIs.

    extract_source -> check_source_file -> load_raw
      -> build_staging -> dq_staging
      -> build_dimensions -> build_state_intervals -> build_fact_incident -> build_reports
      -> dq_marts -> export_tableau_extracts -> validate_kpis -> mark_run_success

`mark_run_failed` watches every task and records a failed run in audit.pipeline_runs.

All logic lives in the `pipeline` package (mounted at /opt/project) so the
same code runs in tests and from the command line (python -m pipeline.cli).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
from airflow.sdk import dag, task

from pipeline import config

DAG_ID = "servicedesk_bi_pipeline"

default_args = {
    "owner": "bi-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


@dag(
    dag_id=DAG_ID,
    description="ServiceNow incidents -> PostgreSQL star schema -> Tableau extract + Superset, with KPI parity checks",
    schedule="@daily",                 # in production this would follow the nightly ServiceNow export
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    template_searchpath=[str(config.SQL_DIR)],
    tags=["servicedesk", "bi-migration", "tableau", "superset"],
    doc_md=__doc__,
)
def servicedesk_bi_pipeline():

    @task
    def extract_source(**context) -> dict:
        """Download the UCI zip (skipped if the CSV is already in data/raw) and log the run."""
        from pipeline import extract, warehouse

        source = extract.download_source()
        with warehouse.connect() as conn:
            warehouse.init_schemas(conn)
            warehouse.start_run(conn, context["run_id"], DAG_ID, source)
        return source

    @task
    def check_source_file() -> dict:
        """File-level contract: exact header, row count, ID and date formats."""
        from pipeline import extract

        return extract.check_source_file()

    @task
    def load_raw() -> int:
        """Full refresh of raw.incident_events with COPY."""
        from pipeline import warehouse

        with warehouse.connect() as conn:
            return warehouse.load_raw(conn)

    # One task per SQL step, so a failure points straight at the model that broke
    sql_tasks = {
        step: SQLExecuteQueryOperator(
            task_id=step,
            conn_id=config.WAREHOUSE_CONN_ID,
            sql=list(files),        # a copy: Airflow resolves template files in place
            do_xcom_push=False,
        )
        for step, files in config.SQL_STEPS.items()
    }

    @task
    def dq_staging(**context) -> dict:
        from pipeline import quality, warehouse

        with warehouse.connect() as conn:
            return quality.run_checks(conn, context["run_id"], ["staging"])

    @task
    def dq_marts(**context) -> dict:
        from pipeline import quality, warehouse

        with warehouse.connect() as conn:
            return quality.run_checks(conn, context["run_id"], ["marts", "reports"])

    @task
    def export_tableau_extracts() -> dict:
        """CSV extracts the Tableau workbook reads (Tableau Public cannot query PostgreSQL)."""
        from pipeline import export, warehouse

        with warehouse.connect() as conn:
            return export.export_for_tableau(conn)

    @task
    def validate_kpis(**context) -> dict:
        """Fail the run if any KPI differs between the legacy Tableau logic and the new SQL."""
        from pipeline import validation, warehouse

        with warehouse.connect() as conn:
            return validation.validate(conn, context["run_id"])

    @task
    def mark_run_success(**context) -> dict:
        from pipeline import warehouse

        with warehouse.connect() as conn:
            return warehouse.finish_run(conn, context["run_id"], "success")

    @task(trigger_rule="one_failed")
    def mark_run_failed(**context) -> None:
        from pipeline import warehouse

        with warehouse.connect() as conn:
            warehouse.finish_run(conn, context["run_id"], "failed", notes="See the failed task's log in Airflow")

    extracted = extract_source()
    checked = check_source_file()
    loaded = load_raw()
    staging_checked = dq_staging()
    marts_checked = dq_marts()
    exported = export_tableau_extracts()
    validated = validate_kpis()
    success = mark_run_success()
    failed = mark_run_failed()

    extracted >> checked >> loaded >> sql_tasks["build_staging"] >> staging_checked
    (
        staging_checked
        >> sql_tasks["build_dimensions"]
        >> sql_tasks["build_state_intervals"]
        >> sql_tasks["build_fact_incident"]
        >> sql_tasks["build_reports"]
        >> marts_checked
        >> exported
        >> validated
        >> success
    )

    # The watcher runs only if something upstream failed
    for upstream in [extracted, checked, loaded, staging_checked, marts_checked, exported, validated,
                     *sql_tasks.values()]:
        upstream >> failed


servicedesk_bi_pipeline()
