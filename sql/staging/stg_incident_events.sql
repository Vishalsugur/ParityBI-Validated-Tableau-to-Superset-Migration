-- staging.stg_incident_events
-- One row per event (update) of an incident, typed and cleaned.
--
-- Cleaning rules (documented in docs/data-model.md):
--   * '?' is the dataset's marker for "unknown" -> NULL
--   * timestamps are day-first text ('29/2/2016 01:16') -> timestamp
--   * 'true'/'false' text -> boolean
--   * '2 - Medium' style codes are split into a numeric code and a label
--   * anonymised IDs keep their label, with double spaces collapsed ('Opened by  8' -> 'Opened by 8')
--   * incident_state '-100' is not a valid ServiceNow state -> flagged, kept for traceability
--   * rn_latest = 1 marks the final snapshot of each incident (highest sys_mod_count,
--     then latest update, then last line in the file as a deterministic tie-break)

drop table if exists staging.stg_incident_events;

create table staging.stg_incident_events as
with typed as (
    select
        r.source_row_number,
        trim(r.number)                                                        as incident_number,
        nullif(trim(r.incident_state), '?')                                   as incident_state,
        nullif(r.active, '?')::boolean                                        as is_active,
        nullif(r.reassignment_count, '?')::int                                as reassignment_count,
        nullif(r.reopen_count, '?')::int                                      as reopen_count,
        nullif(r.sys_mod_count, '?')::int                                     as sys_mod_count,
        nullif(r.made_sla, '?')::boolean                                      as made_sla,
        nullif(regexp_replace(r.caller_id, '\s+', ' ', 'g'), '?')             as caller_id,
        nullif(regexp_replace(r.opened_by, '\s+', ' ', 'g'), '?')             as opened_by,
        to_timestamp(nullif(r.opened_at, '?'), 'DD/MM/YYYY HH24:MI')::timestamp      as opened_at,
        nullif(regexp_replace(r.sys_created_by, '\s+', ' ', 'g'), '?')        as sys_created_by,
        to_timestamp(nullif(r.sys_created_at, '?'), 'DD/MM/YYYY HH24:MI')::timestamp as sys_created_at,
        nullif(regexp_replace(r.sys_updated_by, '\s+', ' ', 'g'), '?')        as sys_updated_by,
        to_timestamp(nullif(r.sys_updated_at, '?'), 'DD/MM/YYYY HH24:MI')::timestamp as sys_updated_at,
        nullif(trim(r.contact_type), '?')                                     as contact_type,
        nullif(regexp_replace(r.location, '\s+', ' ', 'g'), '?')              as location,
        nullif(regexp_replace(r.category, '\s+', ' ', 'g'), '?')              as category,
        nullif(regexp_replace(r.subcategory, '\s+', ' ', 'g'), '?')           as subcategory,
        nullif(regexp_replace(r.u_symptom, '\s+', ' ', 'g'), '?')             as symptom,
        nullif(regexp_replace(r.cmdb_ci, '\s+', ' ', 'g'), '?')               as cmdb_ci,
        nullif(split_part(r.impact,   ' - ', 1), '?')::int                    as impact_code,
        nullif(split_part(r.impact,   ' - ', 2), '')                          as impact_label,
        nullif(split_part(r.urgency,  ' - ', 1), '?')::int                    as urgency_code,
        nullif(split_part(r.urgency,  ' - ', 2), '')                          as urgency_label,
        nullif(split_part(r.priority, ' - ', 1), '?')::int                    as priority_code,
        nullif(split_part(r.priority, ' - ', 2), '')                          as priority_label,
        nullif(regexp_replace(r.assignment_group, '\s+', ' ', 'g'), '?')      as assignment_group,
        nullif(regexp_replace(r.assigned_to, '\s+', ' ', 'g'), '?')           as assigned_to,
        nullif(r.knowledge, '?')::boolean                                     as knowledge_used,
        nullif(r.u_priority_confirmation, '?')::boolean                       as priority_confirmed,
        nullif(trim(r.notify), '?')                                           as notify,
        nullif(regexp_replace(r.problem_id, '\s+', ' ', 'g'), '?')            as problem_id,
        nullif(regexp_replace(r.rfc, '\s+', ' ', 'g'), '?')                   as rfc,
        nullif(regexp_replace(r.vendor, '\s+', ' ', 'g'), '?')                as vendor,
        nullif(regexp_replace(r.caused_by, '\s+', ' ', 'g'), '?')             as caused_by,
        nullif(regexp_replace(r.closed_code, '\s+', ' ', 'g'), '?')           as close_code,
        nullif(regexp_replace(r.resolved_by, '\s+', ' ', 'g'), '?')           as resolved_by,
        to_timestamp(nullif(r.resolved_at, '?'), 'DD/MM/YYYY HH24:MI')::timestamp    as resolved_at,
        to_timestamp(nullif(r.closed_at, '?'), 'DD/MM/YYYY HH24:MI')::timestamp      as closed_at
    from raw.incident_events r
)
select
    t.*,
    t.incident_state in (
        'New', 'Active', 'Awaiting User Info', 'Awaiting Problem',
        'Awaiting Vendor', 'Awaiting Evidence', 'Resolved', 'Closed'
    )                                                                         as is_valid_state,
    row_number() over (
        partition by t.incident_number
        order by t.sys_mod_count desc, t.sys_updated_at desc nulls last, t.source_row_number desc
    )                                                                         as rn_latest,
    row_number() over (
        partition by t.incident_number
        order by t.sys_mod_count, t.sys_updated_at nulls first, t.source_row_number
    )                                                                         as rn_first
from typed t;

create index on staging.stg_incident_events (incident_number);
analyze staging.stg_incident_events;
