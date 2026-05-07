from __future__ import annotations

import re


DOMAIN_MODEL_MAP = {
    "purchase": {
        "keywords": ["compra", "orden de compra", "proveedor", "po", "purchase"],
        "main_model": "purchase.order",
        "line_model": "purchase.order.line",
    },
    "sale": {
        "keywords": ["venta", "orden de venta", "cotizacion", "pedido de venta", "so", "sale"],
        "main_model": "sale.order",
        "line_model": "sale.order.line",
    },
    "invoice": {
        "keywords": ["factura", "facturacion", "invoice", "boleta", "bill"],
        "main_model": "account.move",
        "line_model": "account.move.line",
    },
    "inventory": {
        "keywords": ["inventario", "picking", "transferencia", "stock"],
        "main_model": "stock.picking",
        "line_model": "stock.move",
    },
    "product": {
        "keywords": ["producto", "productos", "sku"],
        "main_model": "product.product",
        "line_model": None,
    },
    "partner": {
        "keywords": ["cliente", "clientes", "partner", "proveedor", "proveedores"],
        "main_model": "res.partner",
        "line_model": None,
    },
    "knowledge": {
        "keywords": ["politica", "proceso", "manual", "documentacion", "segun", "explica", "como funciona", "que es"],
        "main_model": None,
        "line_model": None,
    },
}


def _has_keyword(value: str, keyword: str) -> bool:
    if len(keyword) <= 2:
        return bool(re.search(rf"\b{re.escape(keyword)}\b", value))
    return keyword in value


def resolve_domain(text: str, entity: dict | None = None) -> str | None:
    if isinstance(entity, dict):
        entity_type = entity.get("type")
        if entity_type == "purchase_order":
            return "purchase"
        if entity_type == "sale_order":
            return "sale"
        if entity_type == "invoice":
            return "invoice"
        if entity_type == "business_document_code":
            return entity.get("target_domain")
        if entity_type == "relative_reference":
            return entity.get("target_domain")

    value = text or ""
    for domain_name, config in DOMAIN_MODEL_MAP.items():
        if any(_has_keyword(value, keyword) for keyword in config["keywords"]):
            return domain_name
    return None
