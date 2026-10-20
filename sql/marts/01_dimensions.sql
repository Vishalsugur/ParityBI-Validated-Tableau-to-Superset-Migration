-- Dimension tables for the star schema.
-- Natural keys are used on purpose: the source IDs are already stable,
-- anonymised labels ('Category 53'), and BI users filter on them directly.

-- Calendar covering the full event log (Feb 2016 - Mar 2017)
drop table if exists marts.dim_date cascade;
create table marts.dim_date as
select
    d::date                                   as date_day,
    extract(isodow from d)::int               as iso_weekday,       -- 1 = Monday
    to_char(d, 'Dy')                          as weekday_name,
    extract(isodow from d) in (6, 7)          as is_weekend,
    date_trunc('week', d)::date               as week_start,        -- weeks start on Monday
    to_char(d, 'IYYY-"W"IW')                  as iso_week,
    date_trunc('month', d)::date              as month_start,
    to_char(d, 'YYYY-MM')                     as year_month,
    extract(quarter from d)::int              as quarter,
    extract(year from d)::int                 as year
from generate_series('2016-02-01'::date, '2017-03-31'::date, interval '1 day') as g(d);
alter table marts.dim_date add primary key (date_day);

-- Priority = f(impact, urgency) in ServiceNow; labels taken from the source
drop table if exists marts.dim_priority cascade;
create table marts.dim_priority as
select distinct
    priority_code,
    priority_label,
    priority_code || ' - ' || priority_label  as priority_name
from staging.stg_incident_events
where priority_code is not null;
alter table marts.dim_priority add primary key (priority_code);

drop table if exists marts.dim_contact_type cascade;
create table marts.dim_contact_type as
select
    contact_type,
    case when contact_type in ('Self service', 'Email') then 'Digital'
         when contact_type in ('Phone', 'IVR')          then 'Phone'
         else 'Other' end                     as channel_group
from (select distinct contact_type from staging.stg_incident_events where contact_type is not null) c;
alter table marts.dim_contact_type add primary key (contact_type);

drop table if exists marts.dim_category cascade;
create table marts.dim_category as
select distinct
    coalesce(category, 'Unknown')             as category
from staging.stg_incident_events;
alter table marts.dim_category add primary key (category);

drop table if exists marts.dim_assignment_group cascade;
create table marts.dim_assignment_group as
select distinct
    coalesce(assignment_group, 'Unassigned')  as assignment_group
from staging.stg_incident_events;
alter table marts.dim_assignment_group add primary key (assignment_group);
