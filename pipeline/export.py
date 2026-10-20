"""Export flat files for Tableau (the legacy BI tool in this migration story).

Tableau Public can only read files, not PostgreSQL, so the pipeline publishes
CSV extracts. Booleans are written as 1/0 so Tableau calculations stay simple
(SUM([made_sla]) / COUNT([incident_number])), and timestamps as
'YYYY-MM-DD HH:MM:SS', which Tableau recognises without extra setup.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pipeline import config

log = logging.getLogger(__name__)

EXPORTS = {
    # Incident grain, analysis window only. Tableau's KPIs are calculated from this file.
    "incidents.csv": """
        select
            incident_number,
            to_char(opened_at, 'YYYY-MM-DD HH24:MI:SS')   as opened_at,
            opened_date,
            opened_week_start,
            opened_month,
            opened_weekday,
            to_char(resolved_at, 'YYYY-MM-DD HH24:MI:SS') as resolved_at,
            to_char(closed_at, 'YYYY-MM-DD HH24:MI:SS')   as closed_at,
            contact_type,
            category,
            subcategory,
            priority,
            priority_code,
            assignment_group,
            knowledge_used::int                           as knowledge_used,
            made_sla::int                                 as made_sla,
            is_resolved::int                              as is_resolved,
            is_first_contact_resolution::int              as is_first_contact_resolution,
            is_reopened::int                              as is_reopened,
            reassignment_count,
            reassignment_bucket,
            reopen_count,
            resolution_hours,
            close_hours,
            awaiting_user_hours,
            -- display helper for Tableau: top-10 categories prefixed with their rank,
            -- so an alphabetical sort is a sort by volume ('11 Other' groups the rest)
            case when r.category_rank <= 10 then lpad(r.category_rank::text, 2, '0') || ' ' || i.category
                 else '11 Other categories' end           as category_top10
        from reports.incidents_analysis i
        join (select category, rank() over (order by count(*) desc, category) as category_rank
              from reports.incidents_analysis group by category) r using (category)
        order by incident_number
    """,
    "backlog_daily.csv": "select * from reports.backlog_daily order by date_day",
    "category_insights.csv": "select * from reports.category_insights order by documentation_priority_rank, category",
}


def export_for_tableau(conn, export_dir: Path = config.EXPORT_DIR) -> dict:
    export_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    with conn.cursor() as cur:
        for filename, query in EXPORTS.items():
            path = export_dir / filename
            with open(path, "w", encoding="utf-8", newline="") as fh:
                cur.copy_expert(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)", fh)
            with open(path, encoding="utf-8") as fh:
                written[filename] = sum(1 for _ in fh) - 1
            log.info("Exported %s rows to %s", written[filename], path)
    return written
