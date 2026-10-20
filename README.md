# ParityBI: Validated Tableau-to-Superset Migration

An end-to-end BI project on **real ServiceNow incident data**: an **Apache Airflow** pipeline loads a public IT service-desk log into **PostgreSQL**, models it as a star schema, checks data quality, and serves the same KPIs to a legacy **Tableau** dashboard and a new, self-hosted **Apache Superset** dashboard. On every run it **proves both dashboards show the same numbers**, and everything is documented for technical and non-technical readers.

It mirrors a common real task: *migrate reporting from Tableau to a self-hosted BI tool without changing a single number, and document it.*

![Service Desk Overview in Superset](docs/images/superset-overview.png)

## What's inside

| | |
|---|---|
| **Data** | Real, anonymised ServiceNow event log of an IT company's service desk ([UCI](https://archive.ics.uci.edu/dataset/498/incident+management+process+enriched+event+log), CC BY 4.0): 141,712 updates of 24,918 incidents |
| **Pipeline** | Apache Airflow 3.3 DAG, 14 tasks: download → file contract → load → staging → star schema → reports → checks → Tableau extract → KPI validation |
| **Warehouse** | PostgreSQL 16, layered `raw → staging → marts → reports`, plus an `audit` schema that records every run, check and comparison |
| **Legacy BI** | Tableau workbook (`tableau/ServiceDesk_Legacy.twbx`), opens in the free Tableau Public app |
| **New BI** | Apache Superset 6.1: 3 dashboards, 24 charts, defined as code and imported automatically |
| **Quality** | 17 data quality checks, 152 automated KPI comparisons per run, 31 tests, CI on GitHub Actions |
| **Docs** | Architecture, data model, KPI dictionary, validation report, insights, end-user guide, Tableau guide, runbook, BI tool evaluation |

## Architecture

```mermaid
flowchart LR
    UCI[(UCI dataset<br/>ServiceNow event log<br/>CSV, 141k rows)] -->|download + file contract| RAW

    subgraph AF[Apache Airflow 3.3 DAG]
        direction LR
        RAW[raw] --> STG[staging<br/>typed + cleaned] --> MARTS[marts<br/>star schema] --> REP[reports<br/>KPI views]
        DQ{{17 data quality<br/>checks}}
        VAL{{KPI parity check<br/>152 comparisons}}
    end

    STG -.-> DQ
    REP -.-> DQ
    REP -->|CSV extract| TAB[Tableau<br/>legacy dashboard]
    REP -->|live SQL, read-only user| SS[Apache Superset<br/>new dashboards]
    TAB -.->|same KPIs?| VAL
    REP -.-> VAL
    DQ --> AUD[(audit schema)]
    VAL --> AUD
    AUD --> SS
```

Everything runs locally in Docker. Details: [docs/architecture.md](docs/architecture.md).

## Quick start

Requirements: Docker Desktop (or Docker Engine + Compose v2) with ~4 GB memory for Docker.

```bash
cp .env.example .env            # then set SUPERSET_SECRET_KEY to a long random string
docker compose up -d --build    # first build takes a few minutes
```

| Service | URL | Login |
|---|---|---|
| Airflow | http://localhost:8080 | `airflow` / `airflow` |
| Superset | http://localhost:8088 | `admin` / `admin` |
| PostgreSQL | `localhost:5432`, database `servicedesk` | `analytics` / `analytics` |

The DAG `servicedesk_bi_pipeline` runs once automatically a minute or two after start-up and downloads the dataset from UCI; the run itself takes under a minute. If the download is blocked, put `incident_event_log.csv` from the [UCI zip](https://archive.ics.uci.edu/static/public/498/incident+management+process+enriched+event+log.zip) into `data/raw/` and trigger the DAG again. Then open the Superset dashboards.

Without Docker (Python 3.11+ and any PostgreSQL):

```bash
pip install -r requirements-dev.txt
WAREHOUSE_DSN=postgresql://user:password@localhost:5432/servicedesk python -m pipeline.cli
```

More: [docs/runbook.md](docs/runbook.md).

## The migration check: same numbers in both tools

The core risk of any BI migration is that the new dashboard quietly shows different numbers. This project tests it on every run:

1. **Legacy logic vs new SQL** (automatic, every run): the Tableau calculated fields are re-implemented independently and run on the exact extract Tableau reads. 8 KPIs × (overall + 14 weeks + 4 priorities) = **152 comparisons, all must match**, or the Airflow run fails.
2. **Real Tableau export vs new SQL** (optional): export the `KPI Validation` sheet from Tableau to `validation/tableau_export.csv`; the next run compares it too. English and German number/date formats are both understood.
3. **Superset vs SQL**: `superset/verify_kpis.py` asks Superset's own query API for the KPIs: 40 values, 0 differences.

Results land in the **Migration QA & Data Health** dashboard. A wrong value fails the pipeline (tested: a single planted wrong number is caught and the run is marked failed).

![Migration QA dashboard](docs/images/superset-migration-qa.png)

Details, including migration traps like week start days and median definitions: [docs/data-quality-and-validation.md](docs/data-quality-and-validation.md).

## What the data says

Full write-up with caveats: [docs/insights.md](docs/insights.md).

- **Every handoff costs time.** Incidents solved without reassignment: median **0.7 h**, 87% within SLA. Three or more handoffs: median **192 h**, 33% within SLA. Better first-line knowledge articles target exactly this gap.
- **Where to write documentation first:** ranking categories by incidents *not* solved at first contact puts Category 26, 53 and 42 on top; Category 23 solves only **13%** at first contact.
- **Waiting for the user** takes **30%** of all open hours before resolution: a case for clearer intake forms and how-to guides.
- **Two tracking changes hide in the data:** the "knowledge article used" flag drops from ~98% to ~1% overnight on **11 Mar 2016**, and SLA measurement changes on **16 Mar 2016** (incidents fixed within 4 hours: 35% "met SLA" before, 99% after). Automatic level-shift checks flag both, and the dashboards say so.

![Knowledge and documentation insights](docs/images/superset-knowledge-insights.png)

## Repository layout

```
airflow/dags/            Airflow DAG (thin: calls the pipeline package)
pipeline/                extract, load, quality checks, Tableau export, KPI validation, CLI runner
sql/                     staging → marts (star schema) → reports, in run order
superset/                dashboards as code: builder script, exported bundle (assets/), init, config
tableau/                 workbook generator and the packaged workbook (.twbx)
validation/              optional real Tableau export goes here
docs/                    documentation (see below)
tests/                   unit, DAG integrity and end-to-end tests
docker-compose.yml       Postgres + Airflow + Superset
```

## Documentation

| Document | For |
|---|---|
| [Architecture](docs/architecture.md) | How the pieces fit and why they were chosen |
| [Data model](docs/data-model.md) | Layers, tables, grain, cleaning rules |
| [KPI dictionary](docs/kpi-dictionary.md) | Every KPI: definition, SQL, Tableau formula, Superset metric |
| [Data quality & validation](docs/data-quality-and-validation.md) | All checks, the parity test, known data issues |
| [Insights](docs/insights.md) | Findings for the service desk and documentation team |
| [Dashboard user guide](docs/user-guide-dashboards.md) | Help-center style guide for dashboard users |
| [Tableau guide](docs/tableau-guide.md) | Open, rebuild or publish the legacy workbook |
| [Runbook](docs/runbook.md) | Operate, rerun, troubleshoot |
| [BI tool evaluation](docs/bi-tool-evaluation.md) | Superset vs Metabase vs Grafana for this use case |

## Data source and licence

*Incident management process enriched event log*, Amaral, C., Fantinato, M. & Peres, S. (2018). UCI Machine Learning Repository, [doi:10.24432/C57S4H](https://doi.org/10.24432/C57S4H), licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Values are anonymised by the source (e.g. "Category 53"). The data is downloaded at run time and not stored in this repository.

## Tech stack

Apache Airflow 3.3 · PostgreSQL 16 · Apache Superset 6.1 · Tableau · Python 3.12 (pandas, psycopg2) · SQL (window functions, percentiles, CTEs) · Docker Compose · pytest · GitHub Actions
