-- marts.fact_incident
-- Grain: one row per incident (final snapshot + measures derived from the full event log).
--
-- Analysis window: incidents opened 29 Feb 2016 - 31 May 2016.
-- Why: incident numbers are sequential. Numbers opened in that window are almost
-- completely present (24,644 incidents), while incidents opened later are a sparse
-- sample (274 across 9 months). Including them would distort trends, so they are
-- kept in the table but flagged with in_analysis_window = false.

drop table if exists marts.fact_incident cascade;

create table marts.fact_incident as
with latest as (
    select * from staging.stg_incident_events where rn_latest = 1
),
first_event as (
    select incident_number,
           priority_code    as initial_priority_code,
           assignment_group as initial_assignment_group
    from staging.stg_incident_events
    where rn_first = 1
),
event_stats as (
    select incident_number,
           count(*)                          as event_count,
           bool_or(not is_valid_state)       as has_invalid_state_event
    from staging.stg_incident_events
    group by incident_number
),
state_time as (
    select incident_number,
           sum(duration_hours) filter (where incident_state = 'Awaiting User Info')                         as awaiting_user_hours,
           sum(duration_hours) filter (where incident_state in ('Awaiting Vendor', 'Awaiting Problem', 'Awaiting Evidence')) as awaiting_other_hours,
           bool_or(incident_state = 'Awaiting User Info')                                                    as was_awaiting_user
    from marts.fact_incident_state_interval
    group by incident_number
)
select
    l.incident_number,
    -- dates
    l.opened_at,
    l.opened_at::date                                                      as opened_date,
    date_trunc('week', l.opened_at)::date                                  as opened_week_start,
    l.resolved_at,
    l.closed_at,
    -- descriptive attributes (final values)
    l.incident_state                                                       as final_state,
    l.contact_type,
    coalesce(l.category, 'Unknown')                                        as category,
    l.subcategory,
    l.symptom,
    l.location,
    l.impact_code,
    l.urgency_code,
    l.priority_code,
    f.initial_priority_code,
    coalesce(l.assignment_group, 'Unassigned')                             as assignment_group,
    f.initial_assignment_group,
    l.assigned_to,
    l.resolved_by,
    l.close_code,
    l.caller_id,
    -- flags
    coalesce(l.knowledge_used, false)                                      as knowledge_used,
    coalesce(l.made_sla, false)                                            as made_sla,
    coalesce(l.priority_confirmed, false)                                  as priority_confirmed,
    l.problem_id is not null                                               as has_problem,
    l.rfc is not null                                                      as has_change_request,
    l.vendor is not null                                                   as has_vendor,
    l.resolved_at is not null                                              as is_resolved,
    (l.reassignment_count = 0 and l.reopen_count = 0)                      as is_first_contact_resolution,
    l.reopen_count > 0                                                     as is_reopened,
    l.priority_code is distinct from f.initial_priority_code               as priority_changed,
    coalesce(s.was_awaiting_user, false)                                   as was_awaiting_user,
    e.has_invalid_state_event,
    l.opened_at >= '2016-02-29' and l.opened_at < '2016-06-01'             as in_analysis_window,
    -- counts
    l.reassignment_count,
    l.reopen_count,
    l.sys_mod_count                                                        as update_count,
    e.event_count,
    -- durations in hours
    round((extract(epoch from (l.resolved_at - l.opened_at)) / 3600.0)::numeric, 4) as resolution_hours,
    round((extract(epoch from (l.closed_at   - l.opened_at)) / 3600.0)::numeric, 4) as close_hours,
    round(coalesce(s.awaiting_user_hours, 0), 4)                           as awaiting_user_hours,
    round(coalesce(s.awaiting_other_hours, 0), 4)                          as awaiting_other_hours
from latest l
join first_event f  using (incident_number)
join event_stats e  using (incident_number)
left join state_time s using (incident_number);

alter table marts.fact_incident add primary key (incident_number);
create index on marts.fact_incident (opened_date);
create index on marts.fact_incident (category);
analyze marts.fact_incident;
