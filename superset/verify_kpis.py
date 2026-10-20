"""Check that Superset's metrics return the same numbers as the SQL KPI views.

The Airflow DAG proves legacy Tableau logic == SQL views. This script closes the
last gap: SQL views == what Superset actually shows (its dataset metrics).

    python superset/verify_kpis.py --url http://localhost:8088 \
        --dsn postgresql://analytics:analytics@localhost:5432/servicedesk
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_dashboards import KPI_METRICS, Superset  # noqa: E402

METRICS = [m for m, *_ in KPI_METRICS]
SQL_NAMES = {"incidents": "incidents_opened"}  # Superset metric name -> KPI view column


def superset_values(api: Superset, groupby: list[str]) -> dict:
    ds = [d for d in api.find("dataset", "table_name", "incidents_analysis")][0]
    payload = {
        "datasource": {"id": ds["id"], "type": "table"},
        "queries": [{"metrics": METRICS, "columns": groupby, "row_limit": 1000, "orderby": []}],
        "result_format": "json", "result_type": "full",
    }
    rows = api.post("/api/v1/chart/data", payload)["result"][0]["data"]
    key = groupby[0] if groupby else None
    return {(row[key] if key else "all"): row for row in rows}


def sql_values(conn, view: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(f"select * from {view}")
        cols = [c.name for c in cur.description]
        return {row[0]: dict(zip(cols, row, strict=True)) for row in cur.fetchall()}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=os.environ.get("SUPERSET_URL", "http://localhost:8088"))
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default=os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin"))
    p.add_argument("--dsn", default=os.environ.get(
        "WAREHOUSE_DSN", "postgresql://analytics:analytics@localhost:5432/servicedesk"))
    args = p.parse_args()

    api = Superset(args.url, args.user, args.password)
    failures, checks = [], 0
    with psycopg2.connect(args.dsn) as conn:
        for groupby, view in [([], "reports.kpi_overall"), (["priority"], "reports.kpi_by_priority")]:
            ss, sq = superset_values(api, groupby), sql_values(conn, view)
            for group, row in sq.items():
                for metric in METRICS:
                    checks += 1
                    a = float(ss[group][metric])
                    b = float(row[SQL_NAMES.get(metric, metric)])
                    if abs(a - b) > 0.001:
                        failures.append((view, group, metric, a, b))
    print(f"{checks} Superset metric values compared with SQL views, {len(failures)} differences")
    for f in failures:
        print("  MISMATCH", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
