-- Dashboard tables that are awkward to compute inside a BI tool.

-- 1) Daily backlog: incidents opened, resolved and still open at end of each day.
--    "Open" = opened on/before the day and not resolved by the end of that day.
--    Incidents without resolved_at count as open until closed_at.
drop table if exists reports.backlog_daily;
create table reports.backlog_daily as
with days as (
    select date_day from marts.dim_date
    where date_day between '2016-02-29' and '2016-07-31'
),
inc as (
    select opened_at, coalesce(resolved_at, closed_at) as done_at
    from reports.incidents_analysis
)
select
    d.date_day,
    (select count(*) from inc where inc.opened_at::date = d.date_day)            as opened,
    (select count(*) from inc where inc.done_at::date = d.date_day)              as resolved,
    (select count(*) from inc
      where inc.opened_at < d.date_day + 1
        and (inc.done_at is null or inc.done_at >= d.date_day + 1))              as open_at_end_of_day
from days d
order by d.date_day;

-- 2) Daily tracking table: the share of incidents flagged "knowledge used" and
--    "SLA met" per day. Used by the Data Health dashboard and by the level-shift
--    data quality check. In this dataset the knowledge flag drops from ~98% to ~1%
--    on 11 Mar 2016 and SLA tracking changes on 16 Mar 2016.
drop table if exists reports.tracking_daily;
create table reports.tracking_daily as
select
    opened_date                                                                          as date_day,
    count(*)                                                                             as incidents,
    round(100.0 * avg(knowledge_used::int), 2)                                           as kb_flag_pct,
    round(100.0 * avg(made_sla::int), 2)                                                 as sla_met_pct,
    round(percentile_cont(0.5) within group (order by resolution_hours)::numeric, 2)     as median_resolution_hours
from reports.incidents_analysis
group by opened_date
order by opened_date;

-- 3) Handoff effect: how resolution time and SLA change with each reassignment.
--    SLA is measured only on incidents opened from 16 Mar 2016, after SLA tracking
--    became consistent (see docs/insights.md).
drop table if exists reports.handoff_effect;
create table reports.handoff_effect as
select
    reassignment_bucket,
    count(*)                                                                             as incidents,
    round(100.0 * count(*) / sum(count(*)) over (), 2)                                   as share_pct,
    round(percentile_cont(0.5) within group (order by resolution_hours)::numeric, 2)     as median_resolution_hours,
    round(100.0 * avg(made_sla::int) filter (where opened_date >= '2016-03-16'), 2)      as sla_met_pct_from_16_mar,
    round(100.0 * avg(is_reopened::int), 2)                                              as reopen_rate_pct
from reports.incidents_analysis
group by reassignment_bucket
order by reassignment_bucket;

-- 4) Category insights for the documentation team.
--    handoff_incidents = incidents that were NOT solved at first contact
--    (reassigned or reopened). Categories with many of them are where
--    first-line knowledge articles are most likely to help. This is a
--    prioritisation heuristic, not a causal estimate.
--    The knowledge flag is deliberately not used here: it is unreliable after 11 Mar 2016.
drop table if exists reports.category_insights;
create table reports.category_insights as
with overall as (
    select avg(is_first_contact_resolution::int) as fcr
    from reports.incidents_analysis
),
per_cat as (
    select
        category,
        count(*)                                                                         as incidents,
        round(100.0 * count(*) / sum(count(*)) over (), 2)                               as share_pct,
        round(percentile_cont(0.5) within group (order by resolution_hours)::numeric, 2) as median_resolution_hours,
        round(100.0 * avg(made_sla::int) filter (where opened_date >= '2016-03-16'), 2)  as sla_met_pct_from_16_mar,
        round(100.0 * avg(is_first_contact_resolution::int), 2)                          as first_contact_resolution_pct,
        round(avg(reassignment_count), 2)                                                as avg_reassignments,
        count(*) filter (where not is_first_contact_resolution)                          as handoff_incidents,
        avg(is_first_contact_resolution::int)                                            as fcr_rate
    from reports.incidents_analysis
    group by category
)
select
    p.category,
    p.incidents,
    p.share_pct,
    p.median_resolution_hours,
    p.sla_met_pct_from_16_mar,
    p.first_contact_resolution_pct,
    p.avg_reassignments,
    p.handoff_incidents,
    rank() over (order by p.handoff_incidents desc)                                       as documentation_priority_rank,
    (p.incidents >= 100 and p.fcr_rate < o.fcr)                                           as below_average_fcr
from per_cat p cross join overall o
order by p.handoff_incidents desc;

-- 5) Where time goes: hours spent per state (analysis-window incidents only).
drop table if exists reports.state_time_summary;
create table reports.state_time_summary as
select
    s.incident_state,
    count(distinct s.incident_number)                                                    as incidents_with_state,
    round(sum(s.duration_hours), 1)                                                      as total_hours,
    round(percentile_cont(0.5) within group (order by s.duration_hours)::numeric, 2)     as median_interval_hours
from marts.fact_incident_state_interval s
join marts.fact_incident f using (incident_number)
where f.in_analysis_window and s.interval_end is not null and s.is_valid_state
group by s.incident_state
order by total_hours desc;
