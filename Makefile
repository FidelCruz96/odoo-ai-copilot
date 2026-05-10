.PHONY: eval-real eval-dry

PYTHON ?= python3

eval-real:
	./scripts/run_real_eval.sh

eval-dry:
	cd odoo_ai_service && $(PYTHON) evals/run_eval.py --dry-run
