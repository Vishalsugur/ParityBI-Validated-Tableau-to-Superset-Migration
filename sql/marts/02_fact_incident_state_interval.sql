-- marts.fact_incident_state_interval
-- Grain: one row per state interval of an incident.
-- Turns the event log into "how long did the incident sit in each state".
--   start = time of the update that set the state (first interval starts at opened_at)
--   end   = time of the next update (NULL for the last, terminal update)
-- Several updates can share a minute, so zero-length intervals are normal.

drop table if exists marts.fact_incident_state_interval cascade;

create table marts.fact_incident_state_interval as
with ordered as (
    select
        e.incident_number,
        e.incident_state,
        e.is_valid_state,
        e.assignment_group,
        e.sys_mod_count,
        case when row_number() over w = 1
             then least(e.opened_at, e.sys_updated_at)
             else e.sys_updated_at end                         as interval_start,
        lead(e.sys_updated_at) over w                          as interval_end,
        row_number() over w                                    as interval_seq
    from staging.stg_incident_events e
    window w as (partition by e.incident_number
                 order by e.sys_updated_at nulls first, e.sys_mod_count, e.source_row_number)
)
select
    incident_number,
    interval_seq,
    incident_state,
    is_valid_state,
    assignment_group,
    sys_mod_count,
    interval_start,
    interval_end,
    greatest(extract(epoch from (interval_end - interval_start)) / 3600.0, 0)::numeric(12, 4) as duration_hours
from ordered;

alter table marts.fact_incident_state_interval add primary key (incident_number, interval_seq);
