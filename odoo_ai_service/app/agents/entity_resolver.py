from __future__ import annotations

import re

from app.agents.types import Entity


PURCHASE_ORDER_RE = re.compile(r"\bpo(?:[-a-z0-9]*\d[-a-z0-9]*)\b", re.I)
SALE_ORDER_RE = re.compile(r"\bso(?:[-a-z0-9]*\d[-a-z0-9]*)\b", re.I)
INVOICE_RE = re.compile(r"\b(?:inv|fact|bill)[-/a-z0-9]*\d+\b", re.I)
BUSINESS_CODE_RE = re.compile(r"\b[a-z]{2,6}\s?\d{2,6}(?:[-/]\d{2,6})+\b", re.I)
SIMPLE_DOCUMENT_CODE_RE = re.compile(r"\b[a-z]\d{4,}\b", re.I)

RELATIVE_REFERENCES = {
    "purchase": ["esta compra", "esa compra", "la compra anterior", "la compra", "esta orden de compra"],
    "sale": ["esta venta", "esa venta", "la venta", "este pedido", "ese pedido"],
    "invoice": ["esta factura", "esa factura", "la factura", "esta boleta", "esa boleta"],
}


def _infer_target_domain(value: str) -> str | None:
    if any(keyword in value for keyword in ("venta", "pedido de venta", "orden de venta", "cotizacion")):
        return "sale"
    if any(keyword in value for keyword in ("factura", "boleta", "invoice")):
        return "invoice"
    if any(keyword in value for keyword in ("compra", "orden de compra", "proveedor")):
        return "purchase"
    return None


def _domain_to_model(domain: str | None) -> str | None:
    if domain == "purchase":
        return "purchase.order"
    if domain == "sale":
        return "sale.order"
    if domain == "invoice":
        return "account.move"
    return None


def resolve_entity(text: str) -> Entity | None:
    value = text or ""
    purchase_match = PURCHASE_ORDER_RE.search(value)
    if purchase_match:
        code = purchase_match.group(0).upper()
        return {
            "type": "purchase_order",
            "code": code,
            "model": "purchase.order",
            "lookup_field": "name",
            "confidence": 0.98,
        }

    sale_match = SALE_ORDER_RE.search(value)
    if sale_match:
        code = sale_match.group(0).upper()
        return {
            "type": "sale_order",
            "code": code,
            "model": "sale.order",
            "lookup_field": "name",
            "confidence": 0.98,
        }

    invoice_match = INVOICE_RE.search(value)
    if invoice_match:
        code = invoice_match.group(0).upper()
        return {
            "type": "invoice",
            "code": code,
            "model": "account.move",
            "lookup_field": "name",
            "confidence": 0.95,
        }

    business_code_match = BUSINESS_CODE_RE.search(value)
    if business_code_match:
        code = " ".join(business_code_match.group(0).upper().split())
        target_domain = _infer_target_domain(value)
        return {
            "type": "business_document_code",
            "code": code,
            "target_domain": target_domain,
            "model": _domain_to_model(target_domain),
            "lookup_field": "name",
            "confidence": 0.9 if target_domain else 0.7,
            "explicit_code": True,
        }

    simple_code_match = SIMPLE_DOCUMENT_CODE_RE.search(value)
    if simple_code_match:
        target_domain = _infer_target_domain(value)
        if target_domain in {"purchase", "sale", "invoice"}:
            code = simple_code_match.group(0).upper()
            return {
                "type": "business_document_code",
                "code": code,
                "target_domain": target_domain,
                "model": _domain_to_model(target_domain),
                "lookup_field": "name",
                "confidence": 0.88,
                "explicit_code": True,
            }

    for target_domain, references in RELATIVE_REFERENCES.items():
        for reference in references:
            if reference in value:
                return {
                    "type": "relative_reference",
                    "target_domain": target_domain,
                    "text": reference,
                    "confidence": 0.9,
                }

    return None
