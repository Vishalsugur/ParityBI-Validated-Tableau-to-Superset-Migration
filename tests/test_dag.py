"""DAG integrity: imports cleanly and has the intended shape. Skipped if Airflow isn't installed."""

from pathlib import Path

import pytest

pytest.importorskip("airflow")

DAG_FOLDER = Path(__file__).resolve().parents[1] / "airflow" / "dags"


@pytest.fixture(scope="module")
def dag():
    from airflow.dag_processing.dagbag import DagBag

    bag = DagBag(dag_folder=str(DAG_FOLDER))
    assert bag.import_errors == {}, bag.import_errors
    return bag.get_dag("servicedesk_bi_pipeline")


def test_dag_loads(dag):
    assert dag is not None
    assert len(dag.tasks) == 14


def test_main_path_order(dag):
    path = ["extract_source", "check_source_file", "load_raw", "build_staging", "dq_staging", "build_dimensions",
            "build_state_intervals", "build_fact_incident", "build_reports", "dq_marts", "export_tableau_extracts",
            "validate_kpis", "mark_run_success"]
    for upstream, downstream in zip(path, path[1:], strict=False):
        assert downstream in dag.get_task(upstream).downstream_task_ids, (upstream, downstream)


def test_failure_watcher_sees_every_step(dag):
    watcher = dag.get_task("mark_run_failed")
    assert str(watcher.trigger_rule) in ("one_failed", "TriggerRule.ONE_FAILED")
    assert len(watcher.upstream_task_ids) == 12
