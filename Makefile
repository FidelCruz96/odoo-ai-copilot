.PHONY: dev dev-rag stop logs health eval-real eval-dry

PYTHON ?= python3
COMPOSE ?= docker compose
ENV_FILE ?= .env
AI_SERVICE_PORT ?= 8001

dev:
	$(COMPOSE) --env-file $(ENV_FILE) up -d --build db web ai_service

dev-rag:
	$(COMPOSE) --env-file $(ENV_FILE) -f docker-compose.yaml -f odoo_ai_service/docker-compose.knowledge.yaml up -d --build db web db_knowledge ai_service

stop:
	$(COMPOSE) --env-file $(ENV_FILE) stop

logs:
	$(COMPOSE) --env-file $(ENV_FILE) logs -f --tail=100 web ai_service

health:
	curl -s http://localhost:$(AI_SERVICE_PORT)/v1/health

eval-real:
	./scripts/run_real_eval.sh

eval-dry:
	cd odoo_ai_service && $(PYTHON) evals/run_eval.py --dry-run
