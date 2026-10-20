"""Run the whole pipeline without Airflow - handy for tests, CI and debugging.

    python -m pipeline.cli            # same steps, same order as the Airflow DAG
    WAREHOUSE_DSN=postgresql://user:pw@host:5432/db python -m pipeline.cli
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime

from pipeline import config, export, extract, quality, validation, warehouse


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    run_id = "cli__" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S")

    source = extract.download_source()
    extract.check_source_file()

    with warehouse.connect() as conn:
        warehouse.init_schemas(conn)
        warehouse.start_run(conn, run_id, "cli", source)
        conn.commit()
        try:
            warehouse.load_raw(conn)
            for step, files in config.SQL_STEPS.items():
                for f in files:
                    warehouse.run_sql_file(conn, f)
                conn.commit()
                if step == "build_staging":
                    quality.run_checks(conn, run_id, ["staging"])
            quality.run_checks(conn, run_id, ["marts", "reports"])
            export.export_for_tableau(conn)
            validation.validate(conn, run_id)
            warehouse.finish_run(conn, run_id, "success")
        except Exception as exc:
            conn.rollback()
            warehouse.finish_run(conn, run_id, "failed", notes=str(exc)[:500])
            conn.commit()
            raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
