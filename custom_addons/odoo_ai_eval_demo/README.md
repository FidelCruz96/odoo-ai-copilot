Odoo AI Eval Demo Data
======================

Fixtures reproducibles para los evals de odoo_ai_service/evals.

Este modulo no debe instalarse en produccion. Crea registros con nombres
estables usados por el dataset:

* DCN 0426-0039 en sale.order
* PO-I-10-00026 en purchase.order
* INV/2026/00001 en account.move

Instalacion local:

docker exec odoo18_web_test /opt/odoo/odoo/odoo-bin -d admin -i odoo_ai_eval_demo --stop-after-init --db_host db --db_port 5432 --db_user odoo --db_password odoo

Luego:

docker exec ai_service_test python evals/run_eval.py --url http://127.0.0.1:8000/v1/ask --report evals/reports/latest-real.json
