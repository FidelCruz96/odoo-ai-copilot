from __future__ import annotations

import logging
from datetime import date


_logger = logging.getLogger(__name__)

SALE_ORDER_NAME = "DCN 0426-0039"
PURCHASE_ORDER_NAME = "PO-I-10-00026"
INVOICE_NAME = "INV/2026/00001"


def _get_company(env):
    return env.company or env.ref("base.main_company")


def _get_partner(env, name, supplier_rank=0, customer_rank=0):
    partner = env["res.partner"].search([("name", "=", name)], limit=1)
    values = {
        "name": name,
        "company_type": "company",
        "supplier_rank": supplier_rank,
        "customer_rank": customer_rank,
    }
    if partner:
        partner.write(values)
        return partner
    return env["res.partner"].create(values)


def _get_product(env):
    product = env["product.product"].search([("default_code", "=", "AI-EVAL-SERVICE")], limit=1)
    values = {
        "name": "AI Eval Service",
        "default_code": "AI-EVAL-SERVICE",
        "list_price": 66937.86,
        "standard_price": 100.0,
        "sale_ok": True,
        "purchase_ok": True,
    }
    if "detailed_type" in env["product.template"]._fields:
        values["detailed_type"] = "service"
    elif "type" in env["product.template"]._fields:
        values["type"] = "service"
    if product:
        product.write(values)
        return product
    return env["product.product"].create(values)


def _ensure_sale_order(env, partner, product):
    sale_order = env["sale.order"].search([("name", "=", SALE_ORDER_NAME)], limit=1)
    if sale_order:
        return sale_order

    sale_order = env["sale.order"].create(
        {
            "partner_id": partner.id,
            "date_order": date(2026, 5, 1),
            "order_line": [
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": product.display_name,
                        "product_uom_qty": 1.0,
                        "price_unit": 66937.86,
                    },
                )
            ],
        }
    )
    if sale_order.state in ("draft", "sent"):
        sale_order.action_confirm()
    sale_order.write({"name": SALE_ORDER_NAME})
    return sale_order


def _ensure_purchase_order(env, partner, product):
    purchase_order = env["purchase.order"].search([("name", "=", PURCHASE_ORDER_NAME)], limit=1)
    if purchase_order:
        return purchase_order

    purchase_order = env["purchase.order"].create(
        {
            "partner_id": partner.id,
            "date_order": date(2026, 5, 2),
            "order_line": [
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": product.display_name,
                        "product_qty": 1.0,
                        "price_unit": 122100.0,
                    },
                )
            ],
        }
    )
    if purchase_order.state in ("draft", "sent"):
        purchase_order.button_confirm()
    purchase_order.write({"name": PURCHASE_ORDER_NAME})
    return purchase_order


def _find_income_account(env, company):
    return env["account.account"].search(
        [
            ("company_ids", "in", company.id),
            ("account_type", "=", "income"),
            ("deprecated", "=", False),
        ],
        limit=1,
    )


def _ensure_invoice(env, partner, product, company):
    invoice = env["account.move"].search([("name", "=", INVOICE_NAME), ("move_type", "=", "out_invoice")], limit=1)
    if invoice:
        return invoice

    income_account = _find_income_account(env, company)
    if not income_account:
        _logger.warning("Skipping eval invoice fixture: no income account found for company %s", company.display_name)
        return None

    invoice = env["account.move"].create(
        {
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": date(2026, 5, 3),
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": product.id,
                        "name": product.display_name,
                        "quantity": 1.0,
                        "price_unit": 25000.0,
                        "account_id": income_account.id,
                    },
                )
            ],
        }
    )
    if invoice.state == "draft":
        invoice.action_post()
    invoice.write({"name": INVOICE_NAME})
    return invoice


def post_init_hook(env):
    company = _get_company(env)
    customer = _get_partner(env, "AI Eval Customer", customer_rank=1)
    vendor = _get_partner(env, "AI Eval Vendor", supplier_rank=1)
    product = _get_product(env)

    sale_order = _ensure_sale_order(env, customer, product)
    purchase_order = _ensure_purchase_order(env, vendor, product)
    invoice = _ensure_invoice(env, customer, product, company)

    _logger.info(
        "Odoo AI eval demo data ensured sale_order=%s purchase_order=%s invoice=%s",
        sale_order and sale_order.name,
        purchase_order and purchase_order.name,
        invoice and invoice.name if invoice else None,
    )
