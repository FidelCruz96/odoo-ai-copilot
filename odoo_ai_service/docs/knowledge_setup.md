# Knowledge Setup

Usa el override local para levantar `pgvector` sin tocar el `docker-compose.yaml` principal:

```bash
docker compose -f ../docker-compose.yaml -f docker-compose.knowledge.yaml up -d db_knowledge ai_service
```

Variables mínimas:

```env
OPENAI_API_KEY=your_openai_key_here
KNOWLEDGE_DATABASE_URL=postgresql://odoo:odoo@db_knowledge:5432/knowledge_db
TOP_K=5
SIMILARITY_THRESHOLD=0.70
MAX_UPLOAD_SIZE_MB=10
```

Si alguna variable en tu `.env` tiene caracteres `$`, debes escaparlos como `$$` o Compose intentará interpolarlos y mostrará warnings como `The "xxxxx" variable is not set`.

Después de cambiar dependencias, reconstruye `ai_service`:

```bash
docker compose -f ../docker-compose.yaml -f docker-compose.knowledge.yaml build ai_service
docker compose -f ../docker-compose.yaml -f docker-compose.knowledge.yaml up -d db_knowledge ai_service
```

Prueba sugerida:

```bash
curl -X POST http://localhost:8000/v1/ingest \
  -F "module=purchase" \
  -F "files=@docs/purchase_approvals.md"

curl -X POST http://localhost:8000/v1/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"query":"que es un picking","module":"stock"}'
```
