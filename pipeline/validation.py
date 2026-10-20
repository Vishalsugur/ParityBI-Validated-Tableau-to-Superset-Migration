"""KPI parity check: does the new stack show the same numbers as the legacy Tableau dashboard?

Two references can be compared against the new SQL KPI views (reports.kpi_*):

1. 'tableau_logic' (always): the Tableau workbook's calculated fields re-implemented
   in pandas and run on the same CSV extract Tableau reads. This is an independent
   implementation of every KPI, so a wrong filter, join or aggregation in the new
   SQL shows up as a difference.

2. 'tableau_export' (optional): a crosstab exported from the real Tableau workbook
   (sheet 'KPI Validation'), saved as validation/tableau_export.csv. When present,
   it is compared too. See docs/tableau-guide.md.

Each comparison is stored in audit.kpi_validation; any difference beyond the
tolerance fails the pipeline.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from pipeline import config

log = logging.getLogger(__name__)

# key, caption used in Tableau and Superset, kind
KPIS = [
    ("incidents_opened", "Incidents", "count"),
    ("incidents_resolved", "Resolved incidents", "count"),
    ("median_resolution_hours", "Median resolution (h)", "hours"),
    ("sla_met_pct", "SLA met (%)", "pct"),
    ("first_contact_resolution_pct", "First-contact resolution (%)", "pct"),
    ("kb_usage_pct", "Knowledge used (%)", "pct"),
    ("reopen_rate_pct", "Reopen rate (%)", "pct"),
    ("avg_reassignments", "Avg reassignments", "avg"),
]
KPI_KEYS = [k for k, _, _ in KPIS]
CAPTION_TO_KEY = {caption.lower(): key for key, caption, _ in KPIS}
KIND = {key: kind for key, _, kind in KPIS}

# Allowed absolute difference. SQL rounds to 4 decimals; a Tableau export shows 2.
TOLERANCE = {"tableau_logic": {"count": 0, "hours": 0.001, "pct": 0.001, "avg": 0.001},
             "tableau_export": {"count": 0, "hours": 0.006, "pct": 0.006, "avg": 0.006}}

EXTRACT_FILE = config.EXPORT_DIR / "incidents.csv"
TABLEAU_EXPORT_FILE = config.VALIDATION_DIR / "tableau_export.csv"


# --------------------------------------------------------------------------
# Legacy logic: the Tableau calculated fields, line by line
# --------------------------------------------------------------------------
def _tableau_kpis(group: pd.DataFrame) -> pd.Series:
    n = group["incident_number"].count()                                    # COUNT([incident_number])
    return pd.Series({
        "incidents_opened": n,
        "incidents_resolved": group["is_resolved"].sum(),                    # SUM([is_resolved])
        "median_resolution_hours": group["resolution_hours"].median(),       # MEDIAN([resolution_hours])
        "sla_met_pct": 100 * group["made_sla"].sum() / n,                   # 100*SUM([made_sla])/COUNT(..)
        "first_contact_resolution_pct": 100 * group["is_first_contact_resolution"].sum() / n,
        "kb_usage_pct": 100 * group["knowledge_used"].sum() / n,
        "reopen_rate_pct": 100 * group["is_reopened"].sum() / n,
        "avg_reassignments": group["reassignment_count"].mean(),            # AVG([reassignment_count])
    })


def legacy_kpis_from_extract(path: Path = EXTRACT_FILE) -> pd.DataFrame:
    df = pd.read_csv(path)
    frames = [
        _tableau_kpis(df).to_frame().T.assign(grain="overall", grain_value="all"),
        df.groupby("opened_week_start").apply(_tableau_kpis, include_groups=False)
          .reset_index().rename(columns={"opened_week_start": "grain_value"}).assign(grain="week"),
        df.groupby("priority").apply(_tableau_kpis, include_groups=False)
          .reset_index().rename(columns={"priority": "grain_value"}).assign(grain="priority"),
    ]
    wide = pd.concat(frames, ignore_index=True)
    return _to_long(wide)


# --------------------------------------------------------------------------
# New stack: SQL views that Superset reads
# --------------------------------------------------------------------------
def new_kpis_from_warehouse(conn) -> pd.DataFrame:
    cols = ", ".join(["grain_value"] + KPI_KEYS)
    frames = []
    with conn.cursor() as cur:
        for grain, view in [("overall", "reports.kpi_overall"),
                            ("week", "reports.kpi_weekly"),
                            ("priority", "reports.kpi_by_priority")]:
            cur.execute(f"select {cols} from {view}")
            rows = cur.fetchall()
            frames.append(pd.DataFrame(rows, columns=["grain_value"] + KPI_KEYS).assign(grain=grain))
    return _to_long(pd.concat(frames, ignore_index=True))


def _to_long(wide: pd.DataFrame) -> pd.DataFrame:
    long = wide.melt(id_vars=["grain", "grain_value"], value_vars=KPI_KEYS, var_name="kpi", value_name="value")
    long["grain_value"] = long["grain_value"].astype(str)
    long["value"] = pd.to_numeric(long["value"], errors="coerce").astype(float)
    return long


# --------------------------------------------------------------------------
# Optional: a crosstab exported from the real Tableau workbook
# --------------------------------------------------------------------------
def _parse_number(text, kind: str = "pct") -> float:
    """Read a number as Tableau exports it, in English or German locale.

    Counts have no decimals, so every separator is a thousands separator.
    The other KPIs are exported with 2 decimals, so the LAST separator is the
    decimal point: '1,234.56' and '1.234,56' both give 1234.56.
    """
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return float("nan")
    s = str(text).strip().replace("%", "").replace("\u00a0", "").replace(" ", "").replace("'", "")
    if not s:
        return float("nan")
    if kind == "count":
        return float(re.sub(r"[.,]", "", s))
    last = max(s.rfind(","), s.rfind("."))
    if last == -1:
        return float(s)
    integer, decimals = s[:last], s[last + 1:]
    return float(re.sub(r"[.,]", "", integer) + "." + decimals)


def _parse_weeks(values: pd.Series) -> pd.Series:
    """Tableau exports dates in the user's locale. Accept the variant that yields Mondays."""
    for kwargs in ({"format": "ISO8601"}, {"format": "%d.%m.%Y"}, {"format": "%d/%m/%Y"},
                   {"format": "%m/%d/%Y"}, {"format": "mixed", "dayfirst": False}):
        parsed = pd.to_datetime(values, errors="coerce", **kwargs)
        if parsed.notna().all() and (parsed.dt.dayofweek == 0).all():
            return parsed.dt.strftime("%Y-%m-%d")
    raise ValueError(f"Could not read the week column of the Tableau export: {values.head(3).tolist()}")


def tableau_export_kpis(path: Path = TABLEAU_EXPORT_FILE) -> pd.DataFrame | None:
    if not path.exists():
        return None
    raw = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    week_col = raw.columns[0]
    out = pd.DataFrame({"grain": "week", "grain_value": _parse_weeks(raw[week_col])})
    for col in raw.columns[1:]:
        key = CAPTION_TO_KEY.get(col.strip().lower())
        if key:
            out[key] = raw[col].map(lambda v, k=key: _parse_number(v, KIND[k]))
    found = [k for k in KPI_KEYS if k in out.columns]
    if not found:
        raise ValueError(f"No KPI columns recognised in {path}. Expected captions: {list(CAPTION_TO_KEY)}")
    return out.melt(id_vars=["grain", "grain_value"], value_vars=found, var_name="kpi", value_name="value")


# --------------------------------------------------------------------------
# Compare and record
# --------------------------------------------------------------------------
def compare(legacy: pd.DataFrame, new: pd.DataFrame, reference: str) -> pd.DataFrame:
    merged = legacy.merge(new, on=["grain", "grain_value", "kpi"], how="outer",
                          suffixes=("_legacy", "_new"), indicator=True)
    if reference == "tableau_export":   # an export only covers the weeks/KPIs it contains
        merged = merged[merged["_merge"] != "right_only"]
    merged["tolerance"] = merged["kpi"].map(lambda k: TOLERANCE[reference][KIND[k]])
    merged["abs_diff"] = (merged["value_legacy"] - merged["value_new"]).abs()
    both_null = merged["value_legacy"].isna() & merged["value_new"].isna()
    merged["passed"] = both_null | (merged["abs_diff"] <= merged["tolerance"] + 1e-9)
    merged["reference"] = reference
    return merged[["reference", "grain", "grain_value", "kpi", "value_legacy", "value_new",
                   "abs_diff", "tolerance", "passed"]]


class KpiMismatchError(RuntimeError):
    pass


def validate(conn, run_id: str) -> dict:
    new = new_kpis_from_warehouse(conn)
    results = [compare(legacy_kpis_from_extract(), new, "tableau_logic")]
    exported = tableau_export_kpis()
    if exported is not None:
        log.info("Found %s - comparing the real Tableau export too", TABLEAU_EXPORT_FILE)
        results.append(compare(exported, new, "tableau_export"))
    result = pd.concat(results, ignore_index=True)

    with conn.cursor() as cur:
        cur.execute("delete from audit.kpi_validation where run_id = %s", (run_id,))
        for r in result.itertuples(index=False):
            cur.execute(
                """insert into audit.kpi_validation
                   (run_id, reference, grain, grain_value, kpi, legacy_value, new_value, abs_diff, tolerance, passed)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (run_id, r.reference, r.grain, r.grain_value, r.kpi,
                 None if pd.isna(r.value_legacy) else float(r.value_legacy),
                 None if pd.isna(r.value_new) else float(r.value_new),
                 None if pd.isna(r.abs_diff) else float(r.abs_diff),
                 float(r.tolerance), bool(r.passed)),
            )
    conn.commit()

    failed = result[~result["passed"]]
    summary = {"comparisons": len(result), "failed": len(failed),
               "references": sorted(result["reference"].unique().tolist())}
    log.info("KPI validation: %s", summary)
    if len(failed):
        log.error("Mismatches:\n%s", failed.to_string(index=False))
        raise KpiMismatchError(f"{len(failed)} KPI values differ between legacy and new: see audit.kpi_validation")
    return summary
