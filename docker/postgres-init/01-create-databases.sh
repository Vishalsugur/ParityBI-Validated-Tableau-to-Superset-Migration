#!/bin/bash
# Runs once, the first time the Postgres container starts with an empty volume.
# One server, three databases:
#   airflow      Airflow's metadata
#   superset     Superset's metadata (users, charts, dashboards)
#   servicedesk  the analytics warehouse (owned by 'analytics', read by 'superset_reader')
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE ROLE airflow LOGIN PASSWORD '${AIRFLOW_DB_PASSWORD}';
    CREATE DATABASE airflow OWNER airflow;

    CREATE ROLE superset LOGIN PASSWORD '${SUPERSET_DB_PASSWORD}';
    CREATE DATABASE superset OWNER superset;

    CREATE ROLE analytics LOGIN PASSWORD '${WAREHOUSE_PASSWORD}';
    CREATE DATABASE servicedesk OWNER analytics;

    -- Read-only user for Superset: can see everything the pipeline creates, change nothing
    CREATE ROLE superset_reader LOGIN PASSWORD '${READER_PASSWORD}';
    GRANT CONNECT ON DATABASE servicedesk TO superset_reader;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname servicedesk <<-EOSQL
    ALTER DEFAULT PRIVILEGES FOR ROLE analytics GRANT USAGE ON SCHEMAS TO superset_reader;
    ALTER DEFAULT PRIVILEGES FOR ROLE analytics GRANT SELECT ON TABLES TO superset_reader;
EOSQL
