-- reports.incident_wide
-- One row per incident with dimension labels joined in.
-- This is the single dataset both BI tools read:
--   * Superset uses it as its main dataset (metrics are defined on top of it)
--   * Tableau reads the CSV export of it (exports/tableau/incidents.csv)

drop view if exists reports.incident_wide cascade;

create view reports.incident_wide as
select
    f.incident_number,
    f.opened_at,
    f.opened_date,
    f.opened_week_start,
    d.year_month                                  as opened_month,
    d.weekday_name                                as opened_weekday,
    d.is_weekend                                  as opened_on_weekend,
    f.resolved_at,
    f.closed_at,
    f.contact_type,
    ct.channel_group,
    f.category,
    f.subcategory,
    f.symptom,
    f.location,
    f.priority_code,
    p.priority_name                               as priority,
    f.impact_code,
    f.urgency_code,
    f.assignment_group,
    f.close_code,
    f.knowledge_used,
    f.made_sla,
    f.is_resolved,
    f.is_first_contact_resolution,
    f.is_reopened,
    f.priority_changed,
    f.was_awaiting_user,
    f.has_problem,
    f.has_change_request,
    f.in_analysis_window,
    f.reassignment_count,
    case when f.reassignment_count >= 3 then '3+' else f.reassignment_count::text end as reassignment_bucket,
    f.reopen_count,
    f.update_count,
    f.resolution_hours,
    f.close_hours,
    f.awaiting_user_hours,
    f.awaiting_other_hours
from marts.fact_incident f
left join marts.dim_date d              on d.date_day = f.opened_date
left join marts.dim_priority p          on p.priority_code = f.priority_code
left join marts.dim_contact_type ct     on ct.contact_type = f.contact_type;

-- reports.incidents_analysis
-- The analysis population: incidents opened 29 Feb - 31 May 2016.
-- Superset's main dataset, the KPI views and the Tableau extract all read this
-- view, so every tool starts from exactly the same rows.
create view reports.incidents_analysis as
select * from reports.incident_wide
where in_analysis_window;
