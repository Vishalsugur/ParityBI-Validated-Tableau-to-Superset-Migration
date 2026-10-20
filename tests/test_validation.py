"""KPI parity logic: the legacy (Tableau) calculations, parsing a Tableau export, comparing."""

import pandas as pd
import pytest

from pipeline import validation

EXTRACT_ROWS = [
    # incident_number, opened_week_start, priority, is_resolved, resolution_hours, made_sla, fcr, kb, reopened, reassign
    ("INC1", "2016-02-29", "3 - Moderate", 1, 2.0, 1, 1, 0, 0, 0),
    ("INC2", "2016-02-29", "3 - Moderate", 1, 10.0, 0, 0, 1, 1, 2),
    ("INC3", "2016-03-07", "1 - Critical", 1, 5.0, 1, 1, 0, 0, 0),
    ("INC4", "2016-03-07", "3 - Moderate", 0, None, 0, 0, 0, 0, 3),
]
COLUMNS = ["incident_number", "opened_week_start", "priority", "is_resolved", "resolution_hours", "made_sla",
           "is_first_contact_resolution", "knowledge_used", "is_reopened", "reassignment_count"]


@pytest.fixture
def extract_file(tmp_path):
    path = tmp_path / "incidents.csv"
    pd.DataFrame(EXTRACT_ROWS, columns=COLUMNS).to_csv(path, index=False)
    return path


def value(df, grain, group, kpi):
    row = df[(df.grain == grain) & (df.grain_value == group) & (df.kpi == kpi)]
    assert len(row) == 1, (grain, group, kpi)
    return row.value.iloc[0]


def test_legacy_kpis_follow_tableau_formulas(extract_file):
    df = validation.legacy_kpis_from_extract(extract_file)
    assert value(df, "overall", "all", "incidents_opened") == 4
    assert value(df, "overall", "all", "incidents_resolved") == 3
    assert value(df, "overall", "all", "median_resolution_hours") == 5.0      # nulls ignored, like MEDIAN()
    assert value(df, "overall", "all", "sla_met_pct") == 50.0
    assert value(df, "overall", "all", "avg_reassignments") == 1.25
    assert value(df, "week", "2016-02-29", "median_resolution_hours") == 6.0  # even count -> average of the middle two
    assert value(df, "priority", "1 - Critical", "sla_met_pct") == 100.0


def test_compare_flags_differences():
    legacy = pd.DataFrame({"grain": ["overall"] * 2, "grain_value": ["all"] * 2,
                           "kpi": ["incidents_opened", "sla_met_pct"], "value": [100.0, 63.40]})
    new = legacy.assign(value=[101.0, 63.4004])
    result = validation.compare(legacy, new, "tableau_logic").set_index("kpi")
    assert not result.loc["incidents_opened", "passed"]      # counts must match exactly
    assert result.loc["sla_met_pct", "passed"]                # within 0.001


def test_compare_flags_missing_groups():
    legacy = pd.DataFrame({"grain": ["week"], "grain_value": ["2016-02-29"], "kpi": ["incidents_opened"],
                           "value": [10.0]})
    new = pd.DataFrame({"grain": ["week"], "grain_value": ["2016-03-07"], "kpi": ["incidents_opened"],
                        "value": [10.0]})
    result = validation.compare(legacy, new, "tableau_logic")
    assert (~result.passed).sum() == 2                       # one week missing on each side


def test_week_start_trap_is_caught(extract_file):
    """A dashboard that groups weeks Sunday-Saturday (Tableau's US default) disagrees with Monday weeks."""
    df = pd.read_csv(extract_file)
    monday = validation.legacy_kpis_from_extract(extract_file)
    shifted = df.assign(opened_week_start=(pd.to_datetime(df.opened_week_start) - pd.Timedelta(days=1))
                        .dt.strftime("%Y-%m-%d"))
    shifted_path = extract_file.with_name("shifted.csv")
    shifted.to_csv(shifted_path, index=False)
    sunday = validation.legacy_kpis_from_extract(shifted_path)
    result = validation.compare(sunday, monday, "tableau_logic")
    assert not result[result.grain == "week"].passed.any()


@pytest.mark.parametrize("text,kind,expected", [
    ("1,234.56", "hours", 1234.56), ("1.234,56", "hours", 1234.56), ("63,40", "pct", 63.40),
    ("63.40%", "pct", 63.40), ("24,644", "count", 24644.0), ("24.644", "count", 24644.0),
    ("0.94", "avg", 0.94), ("", "pct", None),
])
def test_parse_number_handles_tableau_locales(text, kind, expected):
    result = validation._parse_number(text, kind)
    if expected is None:
        assert pd.isna(result)
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize("weeks", [
    ["2016-02-29", "2016-03-07"], ["29.02.2016", "07.03.2016"], ["2/29/2016", "3/7/2016"],
    ["February 29, 2016", "March 7, 2016"],
])
def test_parse_weeks_accepts_tableau_date_formats(weeks):
    assert validation._parse_weeks(pd.Series(weeks)).tolist() == ["2016-02-29", "2016-03-07"]


def test_tableau_export_is_read_and_compared(tmp_path, extract_file):
    export = tmp_path / "tableau_export.csv"
    export.write_text(
        "Opened Week Start,Incidents,SLA met (%),Median resolution (h)\n"
        '"29.02.2016",2,"50,00","6,00"\n'
        '"07.03.2016",2,"50,00","5,00"\n', encoding="utf-8")
    exported = validation.tableau_export_kpis(export)
    legacy = validation.legacy_kpis_from_extract(extract_file)
    result = validation.compare(exported, legacy, "tableau_export")
    assert len(result) == 6 and result.passed.all()
