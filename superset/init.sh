#!/usr/bin/env bash
# One-off Superset initialisation (run by the superset-init container).
#   1. create/upgrade Superset's metadata database
#   2. create the admin user (skipped if it already exists)
#   3. import the dashboards bundle from superset/assets, pointing the
#      database connection at the warehouse defined in SUPERSET_WAREHOUSE_URI
set -euo pipefail

ADMIN_USER="${SUPERSET_ADMIN_USER:-admin}"
ADMIN_PASSWORD="${SUPERSET_ADMIN_PASSWORD:-admin}"
ASSETS_DIR="${SUPERSET_ASSETS_DIR:-/app/assets}"
: "${SUPERSET_WAREHOUSE_URI:?SUPERSET_WAREHOUSE_URI must be set}"

echo "==> Upgrading Superset metadata database"
superset db upgrade

echo "==> Creating admin user '${ADMIN_USER}' (ignored if it exists)"
superset fab create-admin \
    --username "${ADMIN_USER}" --password "${ADMIN_PASSWORD}" \
    --firstname Admin --lastname User --email admin@example.com || true

echo "==> Setting up roles and permissions"
superset init

echo "==> Importing dashboards from ${ASSETS_DIR}"
workdir="$(mktemp -d)"
mkdir -p "${workdir}/bundle"
cp -r "${ASSETS_DIR}/." "${workdir}/bundle/"
# The exported bundle masks the password; put the real warehouse URI in place.
for f in "${workdir}"/bundle/databases/*.yaml; do
    python - "$f" <<'PY'
import os, sys, yaml
path = sys.argv[1]
with open(path) as fh:
    doc = yaml.safe_load(fh)
doc["sqlalchemy_uri"] = os.environ["SUPERSET_WAREHOUSE_URI"]
with open(path, "w") as fh:
    yaml.safe_dump(doc, fh, sort_keys=False)
PY
done
(cd "${workdir}" && python -m zipfile -c bundle.zip bundle)
superset import-dashboards --path "${workdir}/bundle.zip" --username "${ADMIN_USER}"
rm -rf "${workdir}"

echo "==> Superset is ready: dashboards imported"
