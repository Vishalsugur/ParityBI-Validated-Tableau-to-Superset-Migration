FROM apache/superset:6.1.0

# The official image ships without database drivers; add the PostgreSQL one
# (used both for Superset's own metadata and for the warehouse connection).
USER root
RUN uv pip install --no-cache --python /app/.venv/bin/python psycopg2-binary
USER superset
