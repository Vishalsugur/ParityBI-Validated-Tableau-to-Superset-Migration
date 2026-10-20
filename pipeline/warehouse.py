"""Warehouse helpers: connections, running SQL files, loading the raw table, run log."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from pipeline import config

log = logging.getLogger(__name__)


@contextmanager
def connect(dsn: str | None = None):
    """Yield a psycopg2 connection.

    Inside Airflow the credentials come from the 'warehouse' connection; elsewhere
    from WAREHOUSE_DSN. The transaction is committed on success, rolled back on error.
    """
    import psycopg2

    if dsn is not None:
        conn = psycopg2.connect(dsn)
    else:
        params = _airflow_connection_params()
        conn = psycopg2.connect(**params) if params else psycopg2.connect(config.WAREHOUSE_DSN)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _airflow_connection_params() -> dict | None:
    """Read host/port/login/password/database from the Airflow connection, if Airflow is present."""
    try:
        from airflow.providers.postgres.hooks.postgres import PostgresHook
    except ImportError:
        return None
    try:
        c = PostgresHook.get_connection(config.WAREHOUSE_CONN_ID)
    except Exception:  # connection not defined -> fall back to WAREHOUSE_DSN
        return None
    return {"host": c.host, "port": c.port or 5432, "user": c.login,
            "password": c.password, "dbname": c.schema}


def run_sql_file(conn, relative_path: str) -> None:
    path = config.SQL_DIR / relative_path
    log.info("Running %s", path)
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))


def init_schemas(conn) -> None:
    run_sql_file(conn, "00_schemas.sql")


def load_raw(conn, csv_path: Path = config.SOURCE_FILE) -> int:
    """Full refresh of raw.incident_events with PostgreSQL COPY (fast, ~1s)."""
    run_sql_file(conn, "01_raw.sql")
    columns = ", ".join(config.EXPECTED_COLUMNS)
    copy_sql = f"COPY raw.incident_events ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with conn.cursor() as cur, open(csv_path, encoding="utf-8") as fh:
        cur.copy_expert(copy_sql, fh)
        cur.execute("select count(*) from raw.incident_events")
        rows = cur.fetchone()[0]
    log.info("Loaded %s rows into raw.incident_events", rows)
    return rows


def start_run(conn, run_id: str, dag_id: str, source: dict | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            insert into audit.pipeline_runs (run_id, dag_id, status, source_file, source_sha256)
            values (%s, %s, 'running', %s, %s)
            on conflict (run_id) do update
               set started_at = now(), finished_at = null, status = 'running',
                   source_file = excluded.source_file, source_sha256 = excluded.source_sha256
            """,
            (run_id, dag_id, (source or {}).get("path"), (source or {}).get("sha256")),
        )


def finish_run(conn, run_id: str, status: str, notes: str | None = None) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """
            update audit.pipeline_runs r
               set finished_at = now(),
                   status = %(status)s,
                   notes = %(notes)s,
                   raw_rows = (select count(*) from raw.incident_events),
                   incidents = (select count(*) from marts.fact_incident),
                   dq_checks_failed = (select count(*) from audit.dq_results d
                                        where d.run_id = r.run_id and not d.passed and d.severity = 'error'),
                   kpi_checks_failed = (select count(*) from audit.kpi_validation k
                                         where k.run_id = r.run_id and not k.passed)
             where run_id = %(run_id)s
            returning raw_rows, incidents, dq_checks_failed, kpi_checks_failed
            """,
            {"status": status, "notes": notes, "run_id": run_id},
        )
        row = cur.fetchone()
    summary = dict(zip(["raw_rows", "incidents", "dq_checks_failed", "kpi_checks_failed"], row or [], strict=False))
    log.info("Run %s finished with status %s: %s", run_id, status, summary)
    return summary
