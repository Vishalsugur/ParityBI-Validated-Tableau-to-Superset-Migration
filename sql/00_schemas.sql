-- Schemas used by the pipeline. Safe to run repeatedly.
--   raw      : source file loaded as-is (all text), one row per CSV line
--   staging  : typed and cleaned event log
--   marts    : star schema (facts + dimensions)
--   reports  : dashboard-ready views/tables shared by Tableau and Superset
--   audit    : pipeline runs, data quality results, KPI validation results

create schema if not exists raw;
create schema if not exists staging;
create schema if not exists marts;
create schema if not exists reports;
create schema if not exists audit;

create table if not exists audit.pipeline_runs (
    run_id            text primary key,
    dag_id            text,
    started_at        timestamptz not null default now(),
    finished_at       timestamptz,
    status            text,
    source_file       text,
    source_sha256     text,
    raw_rows          bigint,
    incidents         bigint,
    dq_checks_failed  int,
    kpi_checks_failed int,
    notes             text
);

create table if not exists audit.dq_results (
    run_id      text,
    checked_at  timestamptz not null default now(),
    layer       text,
    check_name  text,
    description text,
    severity    text,          -- 'error' fails the pipeline, 'warn' is reported only
    failed_rows bigint,
    passed      boolean,
    primary key (run_id, check_name)
);

create table if not exists audit.kpi_validation (
    run_id          text,
    checked_at      timestamptz not null default now(),
    reference       text,      -- which legacy source was compared, e.g. 'tableau_logic' or 'tableau_export'
    grain           text,      -- 'overall', 'week', 'priority'
    grain_value     text,
    kpi             text,
    legacy_value    numeric,
    new_value       numeric,
    abs_diff        numeric,
    tolerance       numeric,
    passed          boolean,
    primary key (run_id, reference, grain, grain_value, kpi)
);
