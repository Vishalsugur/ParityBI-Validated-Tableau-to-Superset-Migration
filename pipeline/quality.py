"""Data quality checks.

Every check is a SQL query that returns ONE number: how many rows break the rule.
0 = pass. 'error' checks stop the pipeline, 'warn' checks are recorded and shown
on the Data Health dashboard but do not stop it.

Results are written to audit.dq_results so every run leaves a trail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Check:
    name: str
    layer: str
    severity: str  # 'error' or 'warn'
    description: str
    sql: str


# Day-over-day jump of a daily percentage, counted on days with >= 100 incidents.
_LEVEL_SHIFT_SQL = """
    with d as (
        select date_day, {col} as pct, incidents,
               lag({col})      over (order by date_day) as prev_pct,
               lag(incidents)  over (order by date_day) as prev_incidents
        from reports.tracking_daily
    )
    select count(*) from d
    where incidents >= 100 and prev_incidents >= 100 and abs(pct - prev_pct) > 40
"""

CHECKS: list[Check] = [
    # ---- staging -----------------------------------------------------------
    Check("staging_row_count_matches_raw", "staging", "error",
          "Every raw row arrives in staging (no rows lost while typing).",
          "select abs((select count(*) from raw.incident_events) - (select count(*) from staging.stg_incident_events))"),
    Check("incident_number_not_null", "staging", "error",
          "Every event has an incident number.",
          "select count(*) from staging.stg_incident_events where incident_number is null"),
    Check("incident_number_format", "staging", "error",
          "Incident numbers look like INC0001234.",
          "select count(*) from staging.stg_incident_events where incident_number !~ '^INC[0-9]{7}$'"),
    Check("opened_at_parsed", "staging", "error",
          "opened_at is present and parsed as a timestamp on every event.",
          "select count(*) from staging.stg_incident_events where opened_at is null"),
    Check("resolved_not_before_opened", "staging", "error",
          "An incident is never resolved before it was opened.",
          "select count(*) from staging.stg_incident_events where resolved_at < opened_at"),
    Check("valid_incident_state", "staging", "warn",
          "incident_state is one of the 8 ServiceNow states (the source contains '-100').",
          "select count(*) from staging.stg_incident_events where not is_valid_state"),
    Check("unique_event_version", "staging", "warn",
          "(incident_number, sys_mod_count) is unique; duplicates are resolved by the latest update.",
          """select count(*) from (select incident_number, sys_mod_count from staging.stg_incident_events
             group by 1, 2 having count(*) > 1) d"""),
    Check("closed_not_before_resolved", "staging", "warn",
          "closed_at is not earlier than resolved_at.",
          "select count(*) from staging.stg_incident_events where closed_at < resolved_at"),
    Check("assignment_group_mostly_filled", "staging", "warn",
          "Fewer than 15% of final incident snapshots have no assignment group (returns the excess count).",
          """select greatest(0, count(*) filter (where assignment_group is null) - 0.15 * count(*))::bigint
             from staging.stg_incident_events where rn_latest = 1"""),
    # ---- marts / reports ---------------------------------------------------
    Check("one_row_per_incident", "marts", "error",
          "fact_incident has exactly one row per incident in staging.",
          """select abs((select count(*) from marts.fact_incident)
                      - (select count(distinct incident_number) from staging.stg_incident_events))"""),
    Check("no_negative_durations", "marts", "error",
          "Resolution, close and waiting times are never negative.",
          """select count(*) from marts.fact_incident
             where resolution_hours < 0 or close_hours < 0 or awaiting_user_hours < 0"""),
    Check("priority_in_dimension", "marts", "error",
          "Every incident priority exists in dim_priority.",
          """select count(*) from marts.fact_incident f
             left join marts.dim_priority p using (priority_code) where p.priority_code is null"""),
    Check("category_in_dimension", "marts", "error",
          "Every incident category exists in dim_category.",
          """select count(*) from marts.fact_incident f
             left join marts.dim_category c using (category) where c.category is null"""),
    Check("intervals_cover_all_events", "marts", "error",
          "The state-interval table has one row per event.",
          """select abs((select count(*) from marts.fact_incident_state_interval)
                      - (select count(*) from staging.stg_incident_events))"""),
    Check("outside_window_share_below_2pct", "marts", "warn",
          "Fewer than 2% of incidents fall outside the analysis window (returns the excess count).",
          """select greatest(0, count(*) filter (where not in_analysis_window) - 0.02 * count(*))::bigint
             from marts.fact_incident"""),
    Check("kb_flag_level_shift", "reports", "warn",
          "Daily share of 'knowledge used' never jumps by more than 40 points day over day "
          "(returns the number of jumps - a sign the field's tracking changed).",
          _LEVEL_SHIFT_SQL.format(col="kb_flag_pct")),
    Check("sla_flag_level_shift", "reports", "warn",
          "Daily share of 'SLA met' never jumps by more than 40 points day over day "
          "(returns the number of jumps - a sign the SLA definition changed).",
          _LEVEL_SHIFT_SQL.format(col="sla_met_pct")),
]


class DataQualityError(RuntimeError):
    pass


def run_checks(conn, run_id: str, layers: list[str]) -> dict:
    """Run all checks of the given layers, store results, raise on failed 'error' checks."""
    selected = [c for c in CHECKS if c.layer in layers]
    results = []
    with conn.cursor() as cur:
        for check in selected:
            cur.execute(check.sql)
            failed_rows = int(cur.fetchone()[0] or 0)
            passed = failed_rows == 0
            results.append((check, failed_rows, passed))
            cur.execute(
                """
                insert into audit.dq_results
                    (run_id, layer, check_name, description, severity, failed_rows, passed)
                values (%s, %s, %s, %s, %s, %s, %s)
                on conflict (run_id, check_name) do update
                   set checked_at = now(), failed_rows = excluded.failed_rows, passed = excluded.passed
                """,
                (run_id, check.layer, check.name, check.description, check.severity, failed_rows, passed),
            )
            level = logging.INFO if passed else (logging.ERROR if check.severity == "error" else logging.WARNING)
            log.log(level, "%-34s %-5s %s (failed rows: %s)",
                    check.name, check.severity, "PASS" if passed else "FAIL", failed_rows)
    conn.commit()

    errors = [c.name for c, _, ok in results if not ok and c.severity == "error"]
    warnings = [c.name for c, _, ok in results if not ok and c.severity == "warn"]
    summary = {"checks": len(results), "errors": errors, "warnings": warnings}
    if errors:
        raise DataQualityError(f"Data quality checks failed: {errors}")
    return summary
