# Choosing the self-hosted BI tool

The brief: replace Tableau for internal service-desk reporting with a **self-hosted, open-source** tool, keep every KPI identical, and keep dashboards maintainable as the team changes. Three common candidates were compared on that brief. Apache Airflow sometimes appears on such shortlists too; it is an orchestrator, not a BI tool, and here it runs the pipeline that feeds whichever BI tool is chosen.

## Criteria and scoring

Scores 1–5 for *this* use case, not in general.

| Criterion | Weight | Apache Superset | Metabase (open source) | Grafana (OSS) |
|---|---|---|---|---|
| Business dashboards (KPIs, bars, tables, filters) | 25% | 5 | 5 | 3 (built for time series and monitoring) |
| SQL-first, works on the existing PostgreSQL views | 15% | 5 (SQL Lab, virtual datasets) | 4 (native questions) | 4 (SQL panels) |
| Metrics defined once, reused by every chart | 15% | 5 (dataset metrics) | 3 (models and metrics, built in the query builder rather than as SQL expressions) | 2 |
| Dashboards as code / version control | 20% | 5 (YAML export/import in the open-source edition) | 2 (serialization is a paid feature) | 5 (JSON provisioning) |
| Ease of use for non-technical users | 15% | 3 | 5 | 3 |
| Licence | 10% | 5 (Apache 2.0) | 4 (AGPL) | 4 (AGPLv3) |
| **Weighted score** | | **4.70** | **3.85** | **3.50** |

## Decision: Apache Superset

- **Dashboards as code in the free edition.** The bundle in `superset/assets/` is imported automatically on a fresh machine, and every change is reviewable in git. For a migration where "same numbers, every time" is the goal, this outweighs Metabase's friendlier editor; Metabase's equivalent (serialization) is only in its paid plans.
- **Semantic layer:** the 8 KPIs are defined once as dataset metrics with the same SQL as the reference views. `superset/verify_kpis.py` proves they match.
- **Same family as the pipeline:** Airflow and Superset are both Apache projects, Python-based, with similar configuration and deployment.

## Trade-offs accepted

- Superset's chart editor is less approachable than Metabase's for occasional users. Mitigation: curated dashboards and a [user guide](user-guide-dashboards.md), so most users only filter and read.
- More moving parts to self-host than Metabase's single container. Mitigation: everything in Docker Compose with health checks and an init container.
- Grafana stays a good choice for operational, real-time monitoring of the pipeline itself; it isn't the best fit for business KPI reporting.

## Sources

- Metabase serialization availability: [Metabase docs, Serialization](https://www.metabase.com/docs/latest/installation-and-operation/serialization)
- Grafana licence change to AGPLv3 (2021): [Grafana licensing](https://grafana.com/licensing/)
- Superset dashboard export/import: Superset CLI `superset import-dashboards` / `export-dashboards`, used in `superset/init.sh`
