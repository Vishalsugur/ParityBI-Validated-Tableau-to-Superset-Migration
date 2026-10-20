# Using the Service Desk dashboards

*For: service desk leads, team managers and the documentation team. No technical knowledge needed.*

The dashboards show how quickly the service desk resolves incidents, where time is lost, and where better documentation would help most. Open them at **http://localhost:8088** and sign in.

There are three dashboards:

| Dashboard | Use it to… |
|---|---|
| **Service Desk Overview** | Check performance at a glance and spot trends |
| **Knowledge & Documentation Insights** | Decide which knowledge articles to write or improve |
| **Migration QA & Data Health** | Confirm the numbers can be trusted |

---

## Service Desk Overview

### The numbers at the top

| Tile | What it means | Good direction |
|---|---|---|
| **Incidents opened** | Incidents reported in the selected period | – |
| **Median resolution (h)** | Half of incidents were fixed faster than this | ↓ lower |
| **SLA met (%)** | Share of incidents resolved within their target time | ↑ higher |
| **First-contact resolution (%)** | Share fixed by the first team, without passing it on and without the user reopening it | ↑ higher |
| **Reopen rate (%)** | Share the user rejected as not fixed | ↓ lower |
| **Avg reassignments** | How often an incident is passed to another team or person, on average | ↓ lower |

Exact definitions are in the [KPI dictionary](kpi-dictionary.md).

### The charts

- **Incidents opened per week**: volume. Weeks start on Monday; the last bar is short because the period ends on Tuesday 31 May.
- **Median resolution time per week**: how fast incidents were fixed, by the week they were *opened*.
- **SLA met & first-contact resolution per week**: the two quality measures side by side.
- **Open incidents at end of day (backlog)**: how many incidents were waiting at the end of each day. A rising line means more came in than were fixed.
- **SLA met & first-contact resolution by priority**: compare Critical, High, Moderate and Low.
- **Top categories**: the busiest categories with their key measures. Click a column header to sort, or use **Search**.

### Filtering

Use the **Filters** panel on the left:

1. Pick one or more values, e.g. **Priority = 1 - Critical**, or set an **Opened (date range)**.
2. Click **Apply filters**. All charts update. The backlog chart follows only the date range; it always shows the whole service desk, not one priority or category.
3. **Clear all** resets the view.

You can also click a bar or a table row to cross-filter the other charts. Click it again to undo.

---

## Knowledge & Documentation Insights

- **Median resolution / SLA met by number of handoffs**: shows how much each handoff costs. Incidents fixed by the first team are typically solved in under an hour.
- **Where to write knowledge articles first**: categories ranked by incidents *not* solved at first contact. Start at the top. A low *First-contact resolution (%)* with a high *Avg reassignments* points to a gap first-line staff can't close on their own today.
- **Open hours before resolution, by state**: where incidents wait. *Awaiting User Info* is time spent waiting for the person who reported the problem; clearer forms and guides reduce it.
- **Daily share flagged 'knowledge used' vs 'SLA met'**: shows the two tracking changes in March 2016 (see FAQ).

---

## Migration QA & Data Health

You don't need this dashboard day to day. It answers *"can I trust these numbers?"*

- **KPI comparisons passed / failed**: every pipeline run recalculates all KPIs the way the old Tableau dashboard does and compares them with these dashboards. **Failed must be 0.**
- **Data quality errors**: must be 0. If it isn't, the data wasn't updated and the dashboards show the last good run.
- **Data quality warnings**: known issues in the source data, documented and expected (currently 4).
- **Pipeline runs**: when the data was last refreshed and whether it worked.

---

## FAQ

**Why does "SLA met" jump in mid-March 2016?**
The way SLA was measured changed on 16 March 2016, not the service itself: resolution times didn't change, but the share marked "met" jumped. Compare SLA only within the same side of that date. From 16 March, 73.9% of incidents met SLA.

**Why does "Knowledge used" drop to almost zero on 11 March 2016?**
The field stopped being filled in the same way. Before 11 March nearly every incident was marked, afterwards almost none. Don't use it to judge whether knowledge articles help.

**Why is the period only March to May 2016?**
The source data is complete only for incidents opened between 29 February and 31 May 2016. Later incidents appear only sporadically, so they are left out to keep trends honest.

**Why do categories have names like "Category 53"?**
The data is a public, anonymised research dataset. Real category names would appear in their place.

**The numbers differ from what I see in Tableau.**
They shouldn't: every refresh checks this automatically. Check the *Migration QA* dashboard. If *KPI comparisons failed* is above 0, tell the BI team; the table below it shows exactly which number differs.

**A chart shows "No results".**
Your filters probably exclude everything, e.g. a category combined with a priority it never had. Click **Clear all**.
