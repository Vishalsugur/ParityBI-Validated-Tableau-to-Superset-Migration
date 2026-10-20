"""Build the Superset dashboards through the REST API ("dashboards as code").

You normally do NOT need to run this: Docker imports the ready-made bundle in
superset/assets/ at start-up. Run it when you change a chart definition here,
then re-export the bundle:

    python superset/build_dashboards.py --url http://localhost:8088 --export superset/assets

What it creates
  * a database connection to the warehouse (read-only user)
  * datasets on the reports/audit schemas, with KPI metrics defined ONCE on the
    main dataset - the same SQL expressions as reports.kpi_* (single definition)
  * 3 dashboards: Service Desk Overview, Knowledge & Documentation Insights,
    Migration QA & Data Health
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import zipfile
from pathlib import Path

import requests

DB_NAME = "Service Desk Warehouse"

# ---------------------------------------------------------------------------
# Semantic layer: KPI metrics (same expressions as sql/reports/02_kpis.sql)
# ---------------------------------------------------------------------------
KPI_METRICS = [
    ("incidents", "COUNT(*)", "Incidents", ",.0f"),
    ("incidents_resolved", "COUNT(*) FILTER (WHERE is_resolved)", "Resolved incidents", ",.0f"),
    ("median_resolution_hours", "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours)",
     "Median resolution (h)", ",.1f"),
    ("sla_met_pct", "100.0 * AVG(made_sla::int)", "SLA met (%)", ",.1f"),
    ("first_contact_resolution_pct", "100.0 * AVG(is_first_contact_resolution::int)",
     "First-contact resolution (%)", ",.1f"),
    ("kb_usage_pct", "100.0 * AVG(knowledge_used::int)", "Knowledge used (%)", ",.1f"),
    ("reopen_rate_pct", "100.0 * AVG(is_reopened::int)", "Reopen rate (%)", ",.2f"),
    ("avg_reassignments", "AVG(reassignment_count)", "Avg reassignments", ",.2f"),
]

LATEST_KPI_VALIDATION_SQL = """
select reference, grain, grain_value, kpi,
       round(legacy_value, 4) as legacy_value, round(new_value, 4) as new_value,
       round(abs_diff, 6) as abs_diff, tolerance,
       passed, case when passed then 'PASS' else 'FAIL' end as result, checked_at, run_id
from audit.kpi_validation
where run_id = (select run_id from audit.kpi_validation order by checked_at desc limit 1)
""".strip()

LATEST_DQ_SQL = """
select layer, check_name, severity, failed_rows, passed,
       case when passed then 'PASS' when severity = 'error' then 'FAIL' else 'WARN' end as result,
       description, checked_at, run_id
from audit.dq_results
where run_id = (select run_id from audit.dq_results order by checked_at desc limit 1)
""".strip()


def adhoc(sql: str, label: str) -> dict:
    return {"expressionType": "SQL", "sqlExpression": sql, "label": label}


class Superset:
    def __init__(self, url: str, user: str, password: str):
        self.url = url.rstrip("/")
        self.s = requests.Session()
        token = self._post_raw("/api/v1/security/login",
                               {"username": user, "password": password, "provider": "db", "refresh": True}
                               )["access_token"]
        self.s.headers.update({"Authorization": f"Bearer {token}", "Referer": self.url})
        csrf = self.s.get(f"{self.url}/api/v1/security/csrf_token/").json()["result"]
        self.s.headers.update({"X-CSRFToken": csrf})

    def _post_raw(self, path, payload):
        r = self.s.post(f"{self.url}{path}", json=payload)
        r.raise_for_status()
        return r.json()

    def get(self, path, **params):
        r = self.s.get(f"{self.url}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def post(self, path, payload):
        r = self.s.post(f"{self.url}{path}", json=payload)
        if not r.ok:
            raise RuntimeError(f"POST {path} failed: {r.status_code} {r.text[:800]}")
        return r.json()

    def put(self, path, payload):
        r = self.s.put(f"{self.url}{path}", json=payload)
        if not r.ok:
            raise RuntimeError(f"PUT {path} failed: {r.status_code} {r.text[:800]}")
        return r.json()

    def delete(self, path):
        self.s.delete(f"{self.url}{path}")

    def find(self, resource: str, column: str, value: str) -> list[dict]:
        """Objects whose `column` equals `value` (filtered client-side: names contain & ( % ...)."""
        found, page = [], 0
        while True:
            batch = self.get(f"/api/v1/{resource}/", q=f"(columns:!(id,{column}),page:{page},page_size:100)")["result"]
            found += [obj for obj in batch if obj.get(column) == value]
            if len(batch) < 100:
                return found
            page += 1


# ---------------------------------------------------------------------------
# Build steps
# ---------------------------------------------------------------------------
def ensure_database(api: Superset, uri: str) -> int:
    for db in api.find("database", "database_name", DB_NAME):
        api.put(f"/api/v1/database/{db['id']}", {"sqlalchemy_uri": uri})
        return db["id"]
    return api.post("/api/v1/database/", {
        "database_name": DB_NAME, "sqlalchemy_uri": uri, "expose_in_sqllab": True,
    })["id"]


def ensure_dataset(api: Superset, db_id: int, schema: str, name: str, sql: str | None = None,
                   dttm: str | None = None, metrics: list | None = None, description: str = "") -> int:
    for ds in api.find("dataset", "table_name", name):
        api.delete(f"/api/v1/dataset/{ds['id']}")
    payload = {"database": db_id, "schema": schema, "table_name": name}
    if sql:
        payload["sql"] = sql
    ds_id = api.post("/api/v1/dataset/", payload)["id"]
    update = {"description": description}
    if dttm:
        update["main_dttm_col"] = dttm
    if metrics:
        update["metrics"] = [
            {"metric_name": m, "expression": e, "verbose_name": v, "d3format": f} for m, e, v, f in metrics
        ]
    api.put(f"/api/v1/dataset/{ds_id}", update)
    label_columns(api, ds_id)
    return ds_id


COLUMN_LABELS = {
    "category": "Category", "priority": "Priority", "assignment_group": "Assignment group",
    "contact_type": "Contact type", "opened_at": "Opened at", "incident_state": "State",
    "reassignment_bucket": "Handoffs", "documentation_priority_rank": "Rank", "incidents": "Incidents",
    "handoff_incidents": "Not solved at first contact", "first_contact_resolution_pct": "First-contact resolution (%)",
    "avg_reassignments": "Avg reassignments", "median_resolution_hours": "Median resolution (h)",
    "sla_met_pct_from_16_mar": "SLA met from 16 Mar (%)", "result": "Result", "grain": "Grain",
    "grain_value": "Group", "kpi": "KPI", "legacy_value": "Legacy (Tableau logic)", "new_value": "New (SQL)",
    "abs_diff": "Difference", "tolerance": "Tolerance", "reference": "Compared with", "layer": "Layer",
    "check_name": "Check", "severity": "Severity", "failed_rows": "Failing rows", "description": "What it checks",
    "started_at": "Started", "status": "Status", "raw_rows": "Raw rows",
    "dq_checks_failed": "DQ errors", "kpi_checks_failed": "KPI mismatches",
}


def label_columns(api: Superset, ds_id: int) -> None:
    """Give dataset columns readable names (shown as table headers and filter labels)."""
    cols = api.get(f"/api/v1/dataset/{ds_id}")["result"]["columns"]
    payload = [{"id": c["id"], "column_name": c["column_name"], "type": c.get("type"),
                "is_dttm": c.get("is_dttm"), "filterable": c.get("filterable", True),
                "groupby": c.get("groupby", True),
                "verbose_name": COLUMN_LABELS.get(c["column_name"], c.get("verbose_name"))} for c in cols]
    api.put(f"/api/v1/dataset/{ds_id}", {"columns": payload})


def create_chart(api: Superset, ds_id: int, name: str, viz: str, params: dict, description: str = "") -> int:
    for ch in api.find("chart", "slice_name", name):
        api.delete(f"/api/v1/chart/{ch['id']}")
    form = {"datasource": f"{ds_id}__table", "viz_type": viz, "time_range": "No filter",
            "adhoc_filters": [], **params}
    return api.post("/api/v1/chart/", {
        "slice_name": name, "viz_type": viz, "datasource_id": ds_id, "datasource_type": "table",
        "params": json.dumps(form), "description": description,
    })["id"]


def big_number(api, ds, name, metric, fmt, subheader=""):
    return create_chart(api, ds, name, "big_number_total", {
        "metric": metric, "y_axis_format": fmt, "subheader": subheader,
        "header_font_size": 0.4, "subheader_font_size": 0.15,
    })


def timeseries(api, ds, name, viz, x, grain, metrics, fmt, extra=None):
    params = {
        "x_axis": x, "time_grain_sqla": grain, "metrics": metrics, "groupby": [],
        "row_limit": 10000, "order_desc": True, "truncate_metric": True,
        "show_legend": len(metrics) > 1, "legendOrientation": "top", "rich_tooltip": True,
        "y_axis_format": fmt, "x_axis_time_format": "%d %b", "markerEnabled": viz.endswith("line"),
        "zoomable": False, "comparison_type": "values",
    }
    params.update(extra or {})
    return create_chart(api, ds, name, viz, params)


def category_bar(api, ds, name, x, metrics, fmt, horizontal=False, sort_by_x=True, extra=None):
    params = {
        "x_axis": x, "metrics": metrics, "groupby": [], "row_limit": 100,
        "orientation": "horizontal" if horizontal else "vertical",
        "x_axis_sort": x if sort_by_x else None, "x_axis_sort_asc": True,
        "show_legend": len(metrics) > 1, "legendOrientation": "top",
        "y_axis_format": fmt, "show_value": True, "rich_tooltip": True, "truncate_metric": True,
    }
    params.update(extra or {})
    return create_chart(api, ds, name, "echarts_timeseries_bar", params)


def table(api, ds, name, columns=None, metrics=None, groupby=None, order_by=None, page_length=10,
          row_limit=200, extra=None):
    if metrics:
        params = {"query_mode": "aggregate", "groupby": groupby or [], "metrics": metrics,
                  "timeseries_limit_metric": order_by, "order_desc": True}
    else:
        params = {"query_mode": "raw", "all_columns": columns,
                  "order_by_cols": [json.dumps([c, asc]) for c, asc in (order_by or [])]}
    params.update({"row_limit": row_limit, "server_page_length": page_length, "include_search": True,
                   "table_timestamp_format": "%Y-%m-%d %H:%M", "show_cell_bars": False})
    params.update(extra or {})
    return create_chart(api, ds, name, "table", params)


# ---------------------------------------------------------------------------
# Dashboard layout helpers
# ---------------------------------------------------------------------------
class Layout:
    def __init__(self, api: Superset, title: str):
        self.api = api
        self.pos = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
            "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
            "HEADER_ID": {"id": "HEADER_ID", "type": "HEADER", "meta": {"text": title}},
        }
        self.n = 0
        self.chart_ids: list[int] = []

    def row(self, items: list[tuple]) -> None:
        """items: ('chart', chart_id, width, height, name) or ('md', markdown, width, height)."""
        self.n += 1
        row_id = f"ROW-{self.n}"
        self.pos["GRID_ID"]["children"].append(row_id)
        self.pos[row_id] = {"type": "ROW", "id": row_id, "children": [],
                            "parents": ["ROOT_ID", "GRID_ID"], "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        for i, item in enumerate(items):
            comp_id = f"{'CHART' if item[0] == 'chart' else 'MARKDOWN'}-{self.n}-{i}"
            self.pos[row_id]["children"].append(comp_id)
            if item[0] == "chart":
                _, chart_id, width, height, name = item
                self.chart_ids.append(chart_id)
                uuid = self.api.get(f"/api/v1/chart/{chart_id}")["result"]["uuid"]
                meta = {"width": width, "height": height, "chartId": chart_id, "sliceName": name, "uuid": uuid}
                ctype = "CHART"
            else:
                _, code, width, height = item
                meta = {"width": width, "height": height, "code": code}
                ctype = "MARKDOWN"
            self.pos[comp_id] = {"type": ctype, "id": comp_id, "children": [],
                                 "parents": ["ROOT_ID", "GRID_ID", row_id], "meta": meta}


def select_filter(fid, name, ds_id, column, charts_in_scope, excluded=()):
    return {
        "id": f"NATIVE_FILTER-{fid}", "name": name, "filterType": "filter_select", "type": "NATIVE_FILTER",
        "targets": [{"datasetId": ds_id, "column": {"name": column}}],
        "controlValues": {"enableEmptyFilter": False, "defaultToFirstItem": False, "multiSelect": True,
                          "searchAllOptions": False, "inverseSelection": False, "sortAscending": True},
        "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
        "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": list(excluded)},
        "chartsInScope": charts_in_scope, "tabsInScope": [], "description": "",
    }


def time_filter(charts_in_scope, excluded=()):
    return {
        "id": "NATIVE_FILTER-opened", "name": "Opened (date range)", "filterType": "filter_time",
        "type": "NATIVE_FILTER", "targets": [{}], "controlValues": {},
        "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
        "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"], "excluded": list(excluded)},
        "chartsInScope": charts_in_scope, "tabsInScope": [], "description": "",
    }


LABEL_COLORS = {
    "SLA met (%)": "#1A85A0", "First-contact resolution (%)": "#4D5BA6", "Knowledge used (%)": "#E5823A",
    "Incidents": "#1A85A0", "Median resolution (h)": "#1A85A0", "Open incidents": "#1A85A0", "Hours": "#4D5BA6",
}


def save_dashboard(api: Superset, title: str, slug: str, layout: Layout, filters: list | None = None,
                   description: str = "") -> int:
    for d in api.find("dashboard", "slug", slug):
        api.delete(f"/api/v1/dashboard/{d['id']}")
    dash_id = api.post("/api/v1/dashboard/", {"dashboard_title": title, "slug": slug, "published": True})["id"]
    meta = {
        "native_filter_configuration": filters or [], "chart_configuration": {},
        "cross_filters_enabled": True, "color_scheme": "supersetColors", "refresh_frequency": 0,
        "expanded_slices": {}, "label_colors": LABEL_COLORS, "timed_refresh_immune_slices": [],
        "default_filters": "{}", "filter_scopes": {}, "shared_label_colors": [],
    }
    api.put(f"/api/v1/dashboard/{dash_id}", {
        "position_json": json.dumps(layout.pos), "json_metadata": json.dumps(meta),
    })
    for chart_id in layout.chart_ids:  # link charts to the dashboard
        api.put(f"/api/v1/chart/{chart_id}", {"dashboards": [dash_id]})
    return dash_id


# ---------------------------------------------------------------------------
# The three dashboards
# ---------------------------------------------------------------------------
OVERVIEW_NOTE = """**Real data:** ServiceNow incident log of an IT service desk (UCI, CC BY 4.0) · **Scope:** 24,644 incidents opened 29 Feb – 31 May 2016 · Weeks start Monday.

**Read with care:** SLA tracking changed on 16 Mar 2016 and the knowledge flag on 11 Mar 2016 – see the *Data Health* dashboard. The same KPIs exist in the legacy Tableau dashboard and are checked automatically on every pipeline run."""

INSIGHTS_NOTE = """### What the documentation team can take from this
1. **Every handoff costs time.** Solved without reassignment: median **0.7 h**. Three or more handoffs: **192 h**. Better first-line knowledge articles target exactly this.
2. **Where to write first:** the table ranks categories by incidents that were *not* solved at first contact.
3. **Waiting for the user:** 30% of all open hours before resolution are spent in *Awaiting User Info* (22% of incidents, median 18 h per wait). Clearer how-to and intake guides target this wait.
4. **The knowledge flag can't measure article impact** in this data: it switches from ~98% to ~1% on 11 Mar 2016 (bottom chart). Fixing this tracking is a prerequisite for measuring documentation impact."""

QA_NOTE = """**Migration QA.** Every pipeline run recalculates all 8 KPIs with the legacy Tableau logic (overall, per week, per priority) and compares them with the new SQL that powers Superset. Any difference fails the run. Data quality checks: *error* stops the pipeline, *warn* is shown here."""


def build(api: Superset, warehouse_uri: str) -> dict[str, int]:
    db = ensure_database(api, warehouse_uri)

    ds_inc = ensure_dataset(api, db, "reports", "incidents_analysis", dttm="opened_at", metrics=KPI_METRICS,
                            description="One row per incident, analysis window only. KPI metrics defined here.")
    ds_backlog = ensure_dataset(api, db, "reports", "backlog_daily", dttm="date_day")
    ds_handoff = ensure_dataset(api, db, "reports", "handoff_effect")
    ds_cat = ensure_dataset(api, db, "reports", "category_insights")
    ds_state = ensure_dataset(api, db, "reports", "state_time_summary")
    ds_track = ensure_dataset(api, db, "reports", "tracking_daily", dttm="date_day")
    ds_kpi = ensure_dataset(api, db, "audit", "latest_kpi_validation", sql=LATEST_KPI_VALIDATION_SQL,
                            dttm="checked_at")
    ds_dq = ensure_dataset(api, db, "audit", "latest_dq_results", sql=LATEST_DQ_SQL, dttm="checked_at")
    ds_runs = ensure_dataset(api, db, "audit", "pipeline_runs", dttm="started_at")

    # ---- 1. Service Desk Overview (the migrated Tableau dashboard) ----------
    c = {}
    c["inc"] = big_number(api, ds_inc, "Incidents opened", "incidents", ",.0f", "in analysis window")
    c["med"] = big_number(api, ds_inc, "Median resolution (h)", "median_resolution_hours", ",.1f", "hours, resolved incidents")
    c["sla"] = big_number(api, ds_inc, "SLA met (%)", "sla_met_pct", ",.1f", "% of incidents")
    c["fcr"] = big_number(api, ds_inc, "First-contact resolution (%)", "first_contact_resolution_pct", ",.1f",
                          "no reassignment, no reopen")
    c["reo"] = big_number(api, ds_inc, "Reopen rate (%)", "reopen_rate_pct", ",.2f", "% of incidents")
    c["rea"] = big_number(api, ds_inc, "Avg reassignments", "avg_reassignments", ",.2f", "per incident")
    c["wk_inc"] = timeseries(api, ds_inc, "Incidents opened per week", "echarts_timeseries_bar",
                             "opened_at", "P1W", ["incidents"], ",.0f")
    c["wk_med"] = timeseries(api, ds_inc, "Median resolution time per week (h)", "echarts_timeseries_line",
                             "opened_at", "P1W", ["median_resolution_hours"], ",.1f")
    c["wk_sla"] = timeseries(api, ds_inc, "SLA met & first-contact resolution per week (%)", "echarts_timeseries_line",
                             "opened_at", "P1W", ["sla_met_pct", "first_contact_resolution_pct"], ",.1f",
                             {"y_axis_bounds": [0, 100]})
    c["backlog"] = timeseries(api, ds_backlog, "Open incidents at end of day (backlog)",
                              "echarts_timeseries_line", "date_day", "P1D",
                              [adhoc("MAX(open_at_end_of_day)", "Open incidents")], ",.0f",
                              {"markerEnabled": False})
    c["prio"] = category_bar(api, ds_inc, "SLA met & first-contact resolution by priority (%)", "priority",
                             ["sla_met_pct", "first_contact_resolution_pct"], ",.1f")
    c["cats"] = table(api, ds_inc, "Top categories", groupby=["category"],
                      metrics=["incidents", "median_resolution_hours", "sla_met_pct",
                               "first_contact_resolution_pct", "avg_reassignments"],
                      order_by="incidents", page_length=10, row_limit=100)
    lo = Layout(api, "Service Desk Overview")
    lo.row([("md", OVERVIEW_NOTE, 12, 14)])
    lo.row([("chart", c[k], 2, 22, n) for k, n in [("inc", "Incidents opened"), ("med", "Median resolution (h)"),
                                                     ("sla", "SLA met (%)"), ("fcr", "First-contact resolution (%)"),
                                                     ("reo", "Reopen rate (%)"), ("rea", "Avg reassignments")]])
    lo.row([("chart", c["wk_inc"], 4, 50, "Incidents opened per week"),
            ("chart", c["wk_med"], 4, 50, "Median resolution time per week (h)"),
            ("chart", c["wk_sla"], 4, 50, "SLA met & first-contact resolution per week (%)")])
    lo.row([("chart", c["backlog"], 6, 50, "Open incidents at end of day (backlog)"),
            ("chart", c["prio"], 6, 50, "SLA met & first-contact resolution by priority (%)")])
    lo.row([("chart", c["cats"], 12, 60, "Top categories")])
    on_incidents = [v for k, v in c.items() if k != "backlog"]
    filters = [
        time_filter(list(c.values())),
        select_filter("priority", "Priority", ds_inc, "priority", on_incidents, excluded=[c["backlog"]]),
        select_filter("category", "Category", ds_inc, "category", on_incidents, excluded=[c["backlog"]]),
        select_filter("group", "Assignment group", ds_inc, "assignment_group", on_incidents, excluded=[c["backlog"]]),
    ]
    d_overview = save_dashboard(api, "Service Desk Overview", "service-desk-overview", lo, filters)

    # ---- 2. Knowledge & Documentation Insights -------------------------------
    k = {}
    k["h_med"] = category_bar(api, ds_handoff, "Median resolution by number of handoffs (h)", "reassignment_bucket",
                              [adhoc("MAX(median_resolution_hours)", "Median resolution (h)")], ",.1f")
    k["h_sla"] = category_bar(api, ds_handoff, "SLA met by number of handoffs (%, from 16 Mar)", "reassignment_bucket",
                              [adhoc("MAX(sla_met_pct_from_16_mar)", "SLA met (%)")], ",.1f")
    k["prio"] = table(api, ds_cat, "Where to write knowledge articles first",
                      columns=["documentation_priority_rank", "category", "incidents", "handoff_incidents",
                               "first_contact_resolution_pct", "avg_reassignments", "median_resolution_hours"],
                      order_by=[("documentation_priority_rank", True)], page_length=10, row_limit=100)
    k["state"] = category_bar(api, ds_state, "Open hours before resolution, by state", "incident_state",
                              [adhoc("SUM(total_hours)", "Hours")], ",.0f", horizontal=True, sort_by_x=False,
                              extra={"x_axis_sort": "Hours", "x_axis_sort_asc": True,
                                     "adhoc_filters": [{"expressionType": "SQL", "clause": "WHERE",
                                                        "sqlExpression": "incident_state NOT IN ('Resolved', 'Closed')"}]})
    k["track"] = timeseries(api, ds_track, "Daily share flagged 'knowledge used' vs 'SLA met' (%)",
                            "echarts_timeseries_line", "date_day", "P1D",
                            [adhoc("MAX(kb_flag_pct)", "Knowledge used (%)"), adhoc("MAX(sla_met_pct)", "SLA met (%)")],
                            ",.0f", {"markerEnabled": False, "y_axis_bounds": [0, 100]})
    lo = Layout(api, "Knowledge & Documentation Insights")
    lo.row([("md", INSIGHTS_NOTE, 12, 25)])
    lo.row([("chart", k["h_med"], 6, 50, "Median resolution by number of handoffs (h)"),
            ("chart", k["h_sla"], 6, 50, "SLA met by number of handoffs (%, from 16 Mar)")])
    lo.row([("chart", k["prio"], 8, 60, "Where to write knowledge articles first"),
            ("chart", k["state"], 4, 60, "Open hours before resolution, by state")])
    lo.row([("chart", k["track"], 12, 50, "Daily share flagged 'knowledge used' vs 'SLA met' (%)")])
    d_insights = save_dashboard(api, "Knowledge & Documentation Insights", "knowledge-insights", lo)

    # ---- 3. Migration QA & Data Health --------------------------------------
    q = {}
    q["passed"] = big_number(api, ds_kpi, "KPI comparisons passed", adhoc("SUM(CASE WHEN passed THEN 1 ELSE 0 END)", "Passed"),
                             ",.0f", "legacy Tableau logic vs new SQL")
    q["failed"] = big_number(api, ds_kpi, "KPI comparisons failed", adhoc("SUM(CASE WHEN passed THEN 0 ELSE 1 END)", "Failed"),
                             ",.0f", "must be 0")
    q["dq_err"] = big_number(api, ds_dq, "Data quality errors",
                             adhoc("SUM(CASE WHEN NOT passed AND severity = 'error' THEN 1 ELSE 0 END)", "Errors"),
                             ",.0f", "error checks failed (stops pipeline)")
    q["dq_warn"] = big_number(api, ds_dq, "Data quality warnings",
                              adhoc("SUM(CASE WHEN NOT passed AND severity = 'warn' THEN 1 ELSE 0 END)", "Warnings"),
                              ",.0f", "known source issues, documented")
    q["kpi_tbl"] = table(api, ds_kpi, "KPI parity: legacy Tableau vs new stack",
                         columns=["result", "grain", "grain_value", "kpi", "legacy_value", "new_value", "abs_diff",
                                  "tolerance", "reference"],
                         order_by=[("passed", True), ("grain", True), ("grain_value", True)], page_length=12,
                         row_limit=1000)
    q["dq_tbl"] = table(api, ds_dq, "Data quality checks (latest run)",
                        columns=["result", "layer", "check_name", "severity", "failed_rows", "description"],
                        order_by=[("passed", True), ("layer", False)], page_length=20, row_limit=100)
    q["runs"] = table(api, ds_runs, "Pipeline runs",
                      columns=["started_at", "status", "raw_rows", "incidents", "dq_checks_failed",
                               "kpi_checks_failed", "run_id"],
                      order_by=[("started_at", False)], page_length=10, row_limit=100)
    lo = Layout(api, "Migration QA & Data Health")
    lo.row([("md", QA_NOTE, 12, 12)])
    lo.row([("chart", q["passed"], 3, 22, "KPI comparisons passed"), ("chart", q["failed"], 3, 22, "KPI comparisons failed"),
            ("chart", q["dq_err"], 3, 22, "Data quality errors"), ("chart", q["dq_warn"], 3, 22, "Data quality warnings")])
    lo.row([("chart", q["kpi_tbl"], 12, 70, "KPI parity: legacy Tableau vs new stack")])
    lo.row([("chart", q["dq_tbl"], 12, 70, "Data quality checks (latest run)")])
    lo.row([("chart", q["runs"], 12, 40, "Pipeline runs")])
    d_qa = save_dashboard(api, "Migration QA & Data Health", "migration-qa", lo)

    return {"overview": d_overview, "insights": d_insights, "qa": d_qa}


def export_bundle(api: Superset, dashboard_ids: list[int], target: Path) -> None:
    """Export Superset's native import bundle (YAML per object) into the repo."""
    q = "!(" + ",".join(str(i) for i in dashboard_ids) + ")"
    r = api.s.get(f"{api.url}/api/v1/dashboard/export/", params={"q": q})
    r.raise_for_status()
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        for member in z.namelist():
            # strip the top-level 'dashboard_export_<timestamp>/' folder
            rel = Path(*Path(member).parts[1:])
            if not rel.parts:
                continue
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(z.read(member))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default=os.environ.get("SUPERSET_URL", "http://localhost:8088"))
    p.add_argument("--user", default=os.environ.get("SUPERSET_ADMIN_USER", "admin"))
    p.add_argument("--password", default=os.environ.get("SUPERSET_ADMIN_PASSWORD", "admin"))
    p.add_argument("--warehouse-uri", default=os.environ.get(
        "SUPERSET_WAREHOUSE_URI", "postgresql+psycopg2://superset_reader:reader@postgres:5432/servicedesk"))
    p.add_argument("--export", type=Path, help="folder to write the import bundle to (e.g. superset/assets)")
    args = p.parse_args()

    api = Superset(args.url, args.user, args.password)
    ids = build(api, args.warehouse_uri)
    print("Dashboards:", ids)
    if args.export:
        export_bundle(api, list(ids.values()), args.export)
        print("Bundle exported to", args.export)


if __name__ == "__main__":
    main()
