"""Central settings. Everything can be overridden with environment variables."""

from __future__ import annotations

import os
from pathlib import Path

# Project root. Inside Docker the repo is mounted at /opt/project.
PROJECT_DIR = Path(os.environ.get("PROJECT_DIR", Path(__file__).resolve().parents[1]))

RAW_DIR = PROJECT_DIR / "data" / "raw"
SQL_DIR = PROJECT_DIR / "sql"
EXPORT_DIR = PROJECT_DIR / "exports" / "tableau"
VALIDATION_DIR = PROJECT_DIR / "validation"

# Source: UCI Machine Learning Repository, dataset 498 (CC BY 4.0)
# "Incident management process enriched event log" - Amaral, Fantinato & Peres (2018)
SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip",
)
SOURCE_FILE = RAW_DIR / "incident_event_log.csv"

# Airflow connection id of the analytics warehouse (PostgreSQL)
WAREHOUSE_CONN_ID = os.environ.get("WAREHOUSE_CONN_ID", "warehouse")

# DSN used when running outside Airflow (pipeline/cli.py, tests)
WAREHOUSE_DSN = os.environ.get(
    "WAREHOUSE_DSN", "postgresql://analytics:analytics@localhost:5432/servicedesk"
)

# Column contract for the source file (order matters: it is loaded with COPY)
EXPECTED_COLUMNS = [
    "number", "incident_state", "active", "reassignment_count", "reopen_count",
    "sys_mod_count", "made_sla", "caller_id", "opened_by", "opened_at",
    "sys_created_by", "sys_created_at", "sys_updated_by", "sys_updated_at",
    "contact_type", "location", "category", "subcategory", "u_symptom", "cmdb_ci",
    "impact", "urgency", "priority", "assignment_group", "assigned_to", "knowledge",
    "u_priority_confirmation", "notify", "problem_id", "rfc", "vendor", "caused_by",
    "closed_code", "resolved_by", "resolved_at", "closed_at",
]

# SQL build order. Each step is one Airflow task.
SQL_STEPS = {
    "build_staging": ["staging/stg_incident_events.sql"],
    "build_dimensions": ["marts/01_dimensions.sql"],
    "build_state_intervals": ["marts/02_fact_incident_state_interval.sql"],
    "build_fact_incident": ["marts/03_fact_incident.sql"],
    "build_reports": [
        "reports/01_incident_wide.sql",
        "reports/02_kpis.sql",
        "reports/03_backlog_and_insights.sql",
    ],
}
