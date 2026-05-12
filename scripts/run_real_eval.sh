#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PG_VERSION="${PG_VERSION:-15}"
export AI_SERVICE_CONTAINER_NAME="${AI_SERVICE_CONTAINER_NAME:-ai_service_test}"
export ODOO_CONTAINER_NAME="${ODOO_CONTAINER_NAME:-odoo18_web_test}"
export KNOWLEDGE_DB_CONTAINER_NAME="${KNOWLEDGE_DB_CONTAINER_NAME:-ai_knowledge_db_test}"

ODOO_DB_NAME="${EVAL_ODOO_DB:-${ODOO_DB:-admin}}"
ODOO_DB_HOST="${EVAL_DB_HOST:-db}"
ODOO_DB_PORT="${EVAL_DB_PORT:-5432}"
ODOO_DB_USER="${EVAL_DB_USER:-${PG_USER:-odoo}}"
ODOO_DB_PASSWORD="${EVAL_DB_PASSWORD:-${PG_PASSWORD:-odoo}}"
ODOO_BIN="${EVAL_ODOO_BIN:-${ODOO_BIN:-/opt/odoo/odoo/odoo-bin}}"
REPORT_PATH="${EVAL_REPORT_PATH:-evals/reports/latest-real.json}"
EVAL_RETRIES="${EVAL_RETRIES:-2}"

COMPOSE_FILES=(-f docker-compose.yaml -f odoo_ai_service/docker-compose.knowledge.yaml)

echo "==> Starting Odoo, AI service, and Knowledge DB"
docker compose "${COMPOSE_FILES[@]}" up -d --build db web db_knowledge ai_service

echo "==> Waiting for AI service health"
for _ in $(seq 1 60); do
  if docker exec "$AI_SERVICE_CONTAINER_NAME" python - <<'PY' >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/v1/health", timeout=2).read()
PY
  then
    break
  fi
  sleep 2
done

docker exec "$AI_SERVICE_CONTAINER_NAME" python - <<'PY'
import urllib.request
urllib.request.urlopen("http://127.0.0.1:8000/v1/health", timeout=5).read()
print("AI service is healthy")
PY

echo "==> Installing eval ERP demo data module"
docker exec "$ODOO_CONTAINER_NAME" "$ODOO_BIN" \
  -d "$ODOO_DB_NAME" \
  -i odoo_ai_assistant,odoo_ai_eval_demo \
  -u odoo_ai_assistant \
  --stop-after-init \
  --db_host "$ODOO_DB_HOST" \
  --db_port "$ODOO_DB_PORT" \
  --db_user "$ODOO_DB_USER" \
  --db_password "$ODOO_DB_PASSWORD"

echo "==> Ingesting Knowledge/RAG demo documents"
docker exec "$AI_SERVICE_CONTAINER_NAME" python - <<'PY'
from pathlib import Path

from app.knowledge.ingest_service import get_ingest_service

service = get_ingest_service()
base = Path("/app/docs")
batches = [
    ("purchase", ["purchase_approvals.md", "purchase_process.md"]),
    ("inventory", ["inventory_process.md"]),
    ("sale", ["sale_process.md"]),
    ("invoice", ["invoice_process.md"]),
]

for module, names in batches:
    files = [(name, (base / name).read_bytes()) for name in names]
    result = service.ingest_files(files, module=module)
    summary = [(item.file, item.chunks, item.status) for item in result.ingested]
    print(module, summary)
PY

echo "==> Running real orchestrator eval"
attempt=1
while true; do
  if docker exec "$AI_SERVICE_CONTAINER_NAME" python evals/run_eval.py \
    --url http://127.0.0.1:8000/v1/ask \
    --report "$REPORT_PATH"; then
    break
  fi

  if [ "$attempt" -ge "$EVAL_RETRIES" ]; then
    echo "Eval failed after $attempt attempt(s)."
    exit 1
  fi

  attempt=$((attempt + 1))
  echo "Eval failed; retrying attempt $attempt/$EVAL_RETRIES after warm-up..."
  sleep 3
done

echo "==> Copying eval report to local workspace"
mkdir -p odoo_ai_service/evals/reports
docker cp "$AI_SERVICE_CONTAINER_NAME:/app/$REPORT_PATH" "odoo_ai_service/$REPORT_PATH"

echo "==> Real eval report: odoo_ai_service/$REPORT_PATH"
