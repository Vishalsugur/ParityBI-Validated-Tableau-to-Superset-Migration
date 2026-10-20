# KPI dictionary

All KPIs use the **analysis population**: incidents opened 29 Feb – 31 May 2016 (`reports.incidents_analysis`, 24,644 incidents). Weeks start on **Monday** and are assigned by the date the incident was **opened**.

Each KPI exists in three places: the SQL reference (`sql/reports/02_kpis.sql`), Tableau calculated fields (`tableau/build_workbook.py`) and Superset dataset metrics (`superset/build_dashboards.py`). The pipeline checks that they agree.

| KPI | Definition | SQL (PostgreSQL / Superset metric) | Tableau calculated field | Value (all) |
|---|---|---|---|---|
| **Incidents** | Incidents opened | `COUNT(*)` | `COUNT([incident_number])` | 24,644 |
| **Resolved incidents** | Incidents with a resolution time | `COUNT(*) FILTER (WHERE is_resolved)` | `SUM([is_resolved])` | 23,098 |
| **Median resolution (h)** | Median of `resolved_at − opened_at` in hours, resolved incidents only | `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY resolution_hours)` | `MEDIAN([resolution_hours])` | 21.98 |
| **SLA met (%)** | Share of incidents whose final `made_sla` flag is true | `100.0 * AVG(made_sla::int)` | `100 * SUM([made_sla]) / COUNT([incident_number])` | 63.40 |
| **First-contact resolution (%)** | Share solved without any reassignment and never reopened | `100.0 * AVG(is_first_contact_resolution::int)` | `100 * SUM([is_first_contact_resolution]) / COUNT([incident_number])` | 54.15 |
| **Knowledge used (%)** | Share with the "knowledge base document used" flag | `100.0 * AVG(knowledge_used::int)` | `100 * SUM([knowledge_used]) / COUNT([incident_number])` | 14.41 |
| **Reopen rate (%)** | Share reopened at least once (caller rejected the fix) | `100.0 * AVG(is_reopened::int)` | `100 * SUM([is_reopened]) / COUNT([incident_number])` | 1.10 |
| **Avg reassignments** | Mean number of group or agent changes per incident | `AVG(reassignment_count)` | `AVG([reassignment_count])` | 0.94 |

## Notes and caveats

**Median, not mean, for resolution time.** Resolution times are very skewed (a few incidents stay open for months). The mean is about 8 times the median and is driven by outliers. PostgreSQL `percentile_cont(0.5)`, Tableau `MEDIAN()` and pandas `median()` all average the two middle values when the count is even, so they agree. Note that PostgreSQL's `percentile_disc` would not.

**SLA met (%): read across 16 March with care.** SLA measurement changes on 16 Mar 2016: incidents fixed in under 4 hours were flagged "SLA met" 35% of the time before, 99% after. The KPI is kept as defined, so it matches the legacy dashboard, but comparisons across that date are not like-for-like. From 16 March the overall value is **73.9%**. Critical and High incidents almost never meet SLA even after the change (1.8% and 0.6%), which is a question for the service desk: tight targets, or a misconfigured SLA clock?

**Knowledge used (%): not usable as an impact measure.** The flag is ~98% until 10 Mar 2016 and ~1% from 11 Mar. The 14% overall is an artefact of those first ten days. It stays in the dictionary because the legacy dashboard reports it.

**First-contact resolution.** Approximated from the data available: no reassignment and no reopening. The source has no explicit "resolved by first line" field.

**Resolution vs close.** `resolved_at` is when the agent fixed the incident; `closed_at` is usually a few days later, when the incident closed automatically. Resolution time is the service measure. 1,546 incidents in the window have no `resolved_at`: they are excluded from the median and counted as not resolved.

**Time zone.** The source has none. Times are used as given, so weeks and days follow the source's local time.

## Other measures on the dashboards

| Measure | Definition | Source |
|---|---|---|
| Open incidents at end of day (backlog) | Opened on/before the day and not resolved by its end; no `resolved_at` → open until `closed_at` | `reports.backlog_daily` |
| Handoff incidents | Incidents not solved at first contact | `reports.category_insights` |
| Documentation priority rank | Rank of a category by handoff incidents (1 = most) | `reports.category_insights` |
| Open hours before resolution, by state | Sum of interval durations per state, excluding *Resolved* and *Closed* | `reports.state_time_summary` |
| SLA met from 16 Mar (%) | SLA met (%) on incidents opened from 16 Mar 2016 only | `reports.handoff_effect`, `reports.category_insights` |
