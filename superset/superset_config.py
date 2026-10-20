"""Superset configuration for the local demo stack (mounted at /app/pythonpath)."""

import os

# Required: a long random string. Set SUPERSET_SECRET_KEY in .env
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "change-me-to-a-long-random-string")

# Superset's own metadata (users, charts, dashboards) lives in PostgreSQL too
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SUPERSET_METADATA_DB_URI",
    "postgresql+psycopg2://superset:superset@postgres:5432/superset",
)

# Native dashboard filters and cross-filtering between charts
FEATURE_FLAGS = {
    "DASHBOARD_CROSS_FILTERS": True,
    "ENABLE_TEMPLATE_PROCESSING": False,
}

# Small local demo: no Redis, simple in-process cache
CACHE_CONFIG = {"CACHE_TYPE": "SimpleCache", "CACHE_DEFAULT_TIMEOUT": 300}
DATA_CACHE_CONFIG = CACHE_CONFIG

WTF_CSRF_ENABLED = True
SUPERSET_WEBSERVER_TIMEOUT = 120
ROW_LIMIT = 50000
