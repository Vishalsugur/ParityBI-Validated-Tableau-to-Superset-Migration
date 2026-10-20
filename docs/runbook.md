# Runbook

## Start and stop

```bash
cp .env.example .env              # once; set SUPERSET_SECRET_KEY
docker compose up -d --build      # start (first build: a few minutes)
docker compose ps                 # all services 'running' / 'healthy'; the two *-init services 'exited (0)'
docker compose down               # stop, keep data
docker compose down -v            # stop and DELETE all databases (fresh start)
```

| Service | URL |
|---|---|
| Airflow | http://localhost:8080 |
| Superset | http://localhost:8088 |
| PostgreSQL | localhost:5432 (`servicedesk` database) |

Memory: give Docker at least 4 GB (Docker Desktop → Settings → Resources).

## Run the pipeline

The DAG `servicedesk_bi_pipeline` runs once after start-up and then daily.

- **Manual run:** Airflow → *servicedesk_bi_pipeline* → **Trigger** (▶).
- **From the command line:** `docker compose exec airflow-scheduler airflow dags trigger servicedesk_bi_pipeline`
- **Without Airflow:** `python -m pipeline.cli` (needs `WAREHOUSE_DSN`, see README).

A successful run takes under a minute. Check the result in Superset → *Migration QA & Data Health*.

## When a run fails

Open the failed (red) task in Airflow → **Logs**. The run is also marked `failed` in `audit.pipeline_runs`.

| Failed task | Likely cause | Fix |
|---|---|---|
| `extract_source` | No internet access to archive.ics.uci.edu | Download the [UCI zip](https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip) manually, put `incident_event_log.csv` in `data/raw/`, trigger again |
| `check_source_file` | File truncated or format changed | Delete `data/raw/incident_event_log.csv` and run again; if it fails again, the source changed: compare the header with `EXPECTED_COLUMNS` in `pipeline/config.py` |
| `build_*` | SQL error after a code change | The log shows the PostgreSQL error and the file; fix the SQL and clear the task |
| `dq_staging` / `dq_marts` | An **error**-level check failed | Superset → Migration QA → *Data quality checks* shows which one and how many rows; or query `audit.dq_results` |
| `validate_kpis` | A KPI differs between legacy and new | Migration QA → *KPI parity* table, sorted with failures first; or query `audit.kpi_validation where not passed` |

After fixing, use **Clear** on the failed task (with downstream) to rerun from there. The pipeline is a full refresh, so rerunning is always safe.

## Change a dashboard

Dashboards are code. Either:

1. Edit in the Superset UI, then export the bundle: Dashboards → select → **Export**, and unzip it into `superset/assets/`; or
2. Change `superset/build_dashboards.py` and run
   `python superset/build_dashboards.py --url http://localhost:8088 --warehouse-uri postgresql+psycopg2://superset_reader:reader@postgres:5432/servicedesk --export superset/assets`

Then `docker compose up -d superset-init` re-imports it. Run `python superset/verify_kpis.py` to confirm the metrics still match the SQL.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `required variable SUPERSET_SECRET_KEY is missing` | Create `.env` from `.env.example` and set the key |
| Port 5432 / 8080 / 8088 already in use | Stop the other program, or set `POSTGRES_PORT=5433` in `.env` (for 8080/8088 change the port mapping in `docker-compose.yml`) |
| Linux: `Permission denied` writing `data/` or `exports/` | Set `AIRFLOW_UID=$(id -u)` in `.env`, then `docker compose up -d` |
| Windows: `bad interpreter` or `\r` errors in init scripts | Line endings were converted. `.gitattributes` prevents it for fresh clones; otherwise run `git add --renormalize .` or convert `*.sh` to LF |
| Superset charts show "relation does not exist" | The pipeline hasn't finished its first run yet; wait or trigger it |
| Airflow UI loads but the DAG is missing | Airflow → *Import errors*; or `docker compose logs airflow-dag-processor` |
| Everything is slow / containers restart | Docker has too little memory; give it 4 GB or more |

## Useful queries

```sql
-- latest runs
select run_id, status, started_at, finished_at, dq_checks_failed, kpi_checks_failed
from audit.pipeline_runs order by started_at desc limit 5;

-- what failed in the last validation
select * from audit.kpi_validation
where run_id = (select run_id from audit.kpi_validation order by checked_at desc limit 1) and not passed;
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -m "not integration"                                    # unit tests, no database needed
TEST_WAREHOUSE_DSN=postgresql://analytics:analytics@localhost:5432/servicedesk pytest -m integration
```

CI (`.github/workflows/ci.yml`) runs lint, unit tests, the end-to-end pipeline on the real dataset, and the DAG integrity test with Airflow 3.3.2.
