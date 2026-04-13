from __future__ import annotations

SEMANTIC_RULES = {
    "ultimos_clientes_creados": {
        "tool": "query_odoo_search",
        "model": "res.partner",
        "required_orderby": "create_date desc",
    },
    "top_vendedor_por_monto": {
        "tool": "query_odoo_group",
        "model": "sale.order",
        "required_groupby": ["user_id"],
        "required_orderby": "amount_total desc",
        "forbidden_orderby": "__count desc",
    },
    "top_vendedor_por_pedidos": {
        "tool": "query_odoo_group",
        "model": "sale.order",
        "required_groupby": ["user_id"],
        "required_orderby": "__count desc",
        "forbidden_fields": ["amount_total:sum"],
    },
    "top_cliente_por_monto": {
        "tool": "query_odoo_group",
        "model": "sale.order",
        "required_groupby": ["partner_id"],
    },
    "top_proveedor_por_compras": {
        "tool": "query_odoo_group",
        "model": "purchase.order",
        "required_groupby": ["partner_id"],
    },
    "producto_mas_comprado": {
        "tool": "query_odoo_group",
        "model": "purchase.order.line",
        "required_groupby": ["product_id"],
    },
    "ventas_total_periodo": {
        "tool": "query_odoo_group",
        "model": "sale.order",
        "required_groupby": [],
        "forbidden_orderby": True,
    },
    "count_clientes": {
        "tool": "query_odoo_count",
        "model": "res.partner",
    },
    "count_ordenes_venta_periodo": {
        "tool": "query_odoo_count",
        "model": "sale.order",
    },
    "facturas_vencidas_count": {
        "tool": "query_odoo_count",
        "model": "account.move",
    },
    "list_facturas_pendientes": {
        "tool": "query_odoo_search",
        "model": "account.move",
        "required_orderby": "invoice_date desc",
    },
    "list_facturas_emitidas_periodo": {
        "tool": "query_odoo_search",
        "model": "account.move",
        "required_orderby": "invoice_date desc",
    },
    "top_proveedor_por_unidades": {
        "tool": "query_odoo_group",
        "model": "purchase.order.line",
        "required_groupby": ["partner_id"],
    },
    "producto_mas_vendido_por_cantidad": {
        "tool": "query_odoo_group",
        "model": "sale.order.line",
        "required_groupby": ["product_id"],
    },
    "producto_mas_vendido_por_monto": {
        "tool": "query_odoo_group",
        "model": "sale.order.line",
        "required_groupby": ["product_id"],
    },
    "promedio_ventas_por_cliente_periodo": {
        "tool": "query_odoo_group",
        "model": "sale.order",
        "required_groupby": ["partner_id"],
    },
    "count_facturas_pendientes": {
        "tool": "query_odoo_count",
        "model": "account.move",
    },
    "count_productos_activos": {
        "tool": "query_odoo_count",
        "model": "product.product",
    },
}


def validate_plan_semantics(intent: str, tool_name: str, arguments: dict) -> str | None:
    if not intent or not isinstance(arguments, dict):
        return None

    rules = SEMANTIC_RULES.get(intent)
    if not rules:
        return None

    if tool_name != rules.get("tool"):
        return f"{intent}_tool_invalida"

    if arguments.get("model") != rules.get("model"):
        return f"{intent}_modelo_invalido"

    required_groupby = rules.get("required_groupby")
    if required_groupby is not None and arguments.get("groupby", []) != required_groupby:
        return f"{intent}_groupby_invalido"

    required_orderby = rules.get("required_orderby")
    if required_orderby and arguments.get("orderby") != required_orderby:
        return f"{intent}_orderby_invalido"

    forbidden_orderby = rules.get("forbidden_orderby")
    if forbidden_orderby is True and arguments.get("orderby"):
        return f"{intent}_orderby_prohibido"
    if isinstance(forbidden_orderby, str) and arguments.get("orderby") == forbidden_orderby:
        return f"{intent}_orderby_prohibido"

    forbidden_fields = set(rules.get("forbidden_fields", []))
    fields = set(arguments.get("fields", []))
    if forbidden_fields.intersection(fields):
        return f"{intent}_fields_invalidos"

    return None
