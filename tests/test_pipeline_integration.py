"""End-to-end run against a real PostgreSQL and the real source file.

Runs only when TEST_WAREHOUSE_DSN is set (CI sets it, see .github/workflows/ci.yml):

    TEST_WAREHOUSE_DSN=postgresql://analytics:analytics@localhost:5432/servicedesk pytest -m integration
"""

import os

import psycopg2
import pytest

DSN = os.environ.get("TEST_WAREHOUSE_DSN")
pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not DSN, reason="set TEST_WAREHOUSE_DSN to run the integration test")]


@pytest.fixture(scope="module")
def warehouse():
    os.environ["WAREHOUSE_DSN"] = DSN
    from pipeline import cli

    assert cli.main() == 0
    conn = psycopg2.connect(DSN)
    yield conn
    conn.close()


def scalar(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def test_all_rows_loaded(warehouse):
    assert scalar(warehouse, "select count(*) from raw.incident_events") == 141712
    assert scalar(warehouse, "select count(*) from marts.fact_incident") == 24918


def test_analysis_window(warehouse):
    assert scalar(warehouse, "select count(*) from reports.incidents_analysis") == 24644


def test_headline_kpis(warehouse):
    with warehouse.cursor() as cur:
        cur.execute("select median_resolution_hours, sla_met_pct, first_contact_resolution_pct from reports.kpi_overall")
        median, sla, fcr = cur.fetchone()
    assert float(median) == pytest.approx(21.975)
    assert float(sla) == pytest.approx(63.3988, abs=1e-3)
    assert float(fcr) == pytest.approx(54.1511, abs=1e-3)


def test_known_source_issues_are_flagged(warehouse):
    with warehouse.cursor() as cur:
        cur.execute("""select check_name, failed_rows from audit.dq_results
                       where run_id = (select run_id from audit.dq_results order by checked_at desc limit 1)
                         and not passed""")
        failed = dict(cur.fetchall())
    assert failed == {"valid_incident_state": 5, "unique_event_version": 5,
                      "kb_flag_level_shift": 1, "sla_flag_level_shift": 1}


def test_every_kpi_matches_legacy_logic(warehouse):
    assert scalar(warehouse, """select count(*) from audit.kpi_validation
                                 where run_id = (select run_id from audit.kpi_validation order by checked_at desc limit 1)
                                   and not passed""") == 0
