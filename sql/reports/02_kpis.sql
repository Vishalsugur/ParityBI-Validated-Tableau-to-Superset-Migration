-- KPI views. These SQL definitions are the reference implementation of the
-- KPI dictionary (docs/kpi-dictionary.md). The validation step compares them
-- with the legacy Tableau logic; Superset metrics use the same expressions.
--
-- Population: incidents in the analysis window (opened 29 Feb - 31 May 2016).

drop view if exists reports.kpi_overall;
drop view if exists reports.kpi_weekly;
drop view if exists reports.kpi_by_priority;

create view reports.kpi_overall as
select
    'all'::text                                                                         as grain_value,
    count(*)                                                                            as incidents_opened,
    count(*) filter (where is_resolved)                                                 as incidents_resolved,
    round(percentile_cont(0.5) within group (order by resolution_hours)::numeric, 4)    as median_resolution_hours,
    round(100.0 * avg(made_sla::int), 4)                                                as sla_met_pct,
    round(100.0 * avg(is_first_contact_resolution::int), 4)                             as first_contact_resolution_pct,
    round(100.0 * avg(knowledge_used::int), 4)                                          as kb_usage_pct,
    round(100.0 * avg(is_reopened::int), 4)                                             as reopen_rate_pct,
    round(avg(reassignment_count), 4)                                                   as avg_reassignments
from reports.incidents_analysis;

create view reports.kpi_weekly as
select
    opened_week_start::text                                                             as grain_value,
    opened_week_start,
    count(*)                                                                            as incidents_opened,
    count(*) filter (where is_resolved)                                                 as incidents_resolved,
    round(percentile_cont(0.5) within group (order by resolution_hours)::numeric, 4)    as median_resolution_hours,
    round(100.0 * avg(made_sla::int), 4)                                                as sla_met_pct,
    round(100.0 * avg(is_first_contact_resolution::int), 4)                             as first_contact_resolution_pct,
    round(100.0 * avg(knowledge_used::int), 4)                                          as kb_usage_pct,
    round(100.0 * avg(is_reopened::int), 4)                                             as reopen_rate_pct,
    round(avg(reassignment_count), 4)                                                   as avg_reassignments
from reports.incidents_analysis
group by opened_week_start
order by opened_week_start;

create view reports.kpi_by_priority as
select
    priority                                                                            as grain_value,
    priority_code,
    count(*)                                                                            as incidents_opened,
    count(*) filter (where is_resolved)                                                 as incidents_resolved,
    round(percentile_cont(0.5) within group (order by resolution_hours)::numeric, 4)    as median_resolution_hours,
    round(100.0 * avg(made_sla::int), 4)                                                as sla_met_pct,
    round(100.0 * avg(is_first_contact_resolution::int), 4)                             as first_contact_resolution_pct,
    round(100.0 * avg(knowledge_used::int), 4)                                          as kb_usage_pct,
    round(100.0 * avg(is_reopened::int), 4)                                             as reopen_rate_pct,
    round(avg(reassignment_count), 4)                                                   as avg_reassignments
from reports.incidents_analysis
group by priority, priority_code
order by priority_code;
