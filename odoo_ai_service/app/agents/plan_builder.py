from __future__ import annotations

from app.agents.route_selector import CLARIFICATION, ERP_DATA, FALLBACK, KNOWLEDGE, MIXED
from app.agents.types import Entity, ToolStep


def _canonical_policy_query(domain: str | None) -> str:
    if domain == "purchase":
        return "politica aprobacion compras monto umbral orden de compra"
    if domain == "sale":
        return "politica proceso ventas aprobacion pedido de venta"
    if domain == "invoice":
        return "politica proceso facturacion aprobacion factura"
    if domain == "inventory":
        return "documentacion funcional picking transferencia stock inventario"
    return "politica proceso documentacion"


def has_odoo_tool(plan: list[ToolStep]) -> bool:
    return any(step.get("tool", "").startswith("query_odoo_") for step in plan)


def has_knowledge_tool(plan: list[ToolStep]) -> bool:
    return any(step.get("tool") == "search_knowledge" for step in plan)


def _main_model_for_domain(domain: str | None) -> str | None:
    if domain == "purchase":
        return "purchase.order"
    if domain == "sale":
        return "sale.order"
    if domain == "invoice":
        return "account.move"
    if domain == "inventory":
        return "stock.picking"
    if domain == "product":
        return "product.product"
    if domain == "partner":
        return "res.partner"
    return None


def _default_domain_for_domain(domain: str | None) -> list:
    if domain == "sale":
        return [["state", "in", ["sale", "done"]]]
    if domain == "purchase":
        return [["state", "in", ["purchase", "done"]]]
    if domain == "invoice":
        return [["move_type", "=", "out_invoice"], ["state", "=", "posted"]]
    return []


def build_plan(route: str, domain: str | None, intent: str | None, entity: Entity | None) -> list[ToolStep]:
    plan: list[ToolStep] = []
    model = entity.get("model") if isinstance(entity, dict) else None
    domain_model = model or _main_model_for_domain(domain)

    if route == CLARIFICATION:
        return []

    if route == ERP_DATA and intent == "amount_lookup":
        if isinstance(entity, dict) and entity.get("id") and model:
            plan.append(
                {
                    "tool": "query_odoo_read",
                    "args": {
                        "model": model,
                        "ids": [entity["id"]],
                        "fields": ["name", "amount_total", "currency_id", "state"],
                    },
                }
            )
        elif isinstance(entity, dict) and entity.get("code") and model:
            plan.extend(
                [
                    {
                        "tool": "query_odoo_search",
                        "args": {
                            "model": model,
                            "domain": [[entity.get("lookup_field", "name"), "=", entity["code"]]],
                            "limit": 1,
                        },
                    },
                    {
                        "tool": "query_odoo_read",
                        "args": {
                            "model": model,
                            "ids": "$previous_result",
                            "fields": ["name", "amount_total", "currency_id", "state"],
                        },
                    },
                ]
            )
    elif route == ERP_DATA and intent == "status_lookup":
        if isinstance(entity, dict) and entity.get("id") and model:
            plan.append(
                {
                    "tool": "query_odoo_read",
                    "args": {
                        "model": model,
                        "ids": [entity["id"]],
                        "fields": ["name", "state"],
                    },
                }
            )
    elif route == ERP_DATA and intent == "count" and domain_model:
        plan.append(
            {
                "tool": "query_odoo_count",
                "args": {
                    "model": domain_model,
                    "domain": _default_domain_for_domain(domain),
                },
            }
        )
    elif route == ERP_DATA and intent == "ranking" and domain in {"sale", "invoice", "purchase"} and domain_model:
        amount_field = "amount_total:sum"
        plan.append(
            {
                "tool": "query_odoo_group",
                "args": {
                    "model": domain_model,
                    "domain": _default_domain_for_domain(domain) + [["partner_id", "!=", False]],
                    "fields": ["partner_id", amount_field],
                    "groupby": ["partner_id"],
                    "orderby": "amount_total desc",
                    "limit": 5,
                },
            }
        )
    elif route == MIXED and intent == "policy_validation":
        if isinstance(entity, dict) and entity.get("id") and model:
            plan.append(
                {
                    "tool": "query_odoo_read",
                    "args": {
                        "model": model,
                        "ids": [entity["id"]],
                        "fields": ["name", "amount_total", "currency_id", "state", "partner_id"],
                    },
                }
            )
        elif isinstance(entity, dict) and entity.get("code") and model:
            plan.extend(
                [
                    {
                        "tool": "query_odoo_search",
                        "args": {
                            "model": model,
                            "domain": [[entity.get("lookup_field", "name"), "=", entity["code"]]],
                            "limit": 1,
                        },
                    },
                    {
                        "tool": "query_odoo_read",
                        "args": {
                            "model": model,
                            "ids": "$previous_result",
                            "fields": ["name", "amount_total", "currency_id", "state", "partner_id"],
                        },
                    },
                ]
            )
        plan.append(
            {
                "tool": "search_knowledge",
                "args": {
                    "query": _canonical_policy_query(domain),
                    "filters": {"module": domain},
                    "top_k": 5,
                },
            }
        )
    elif route == KNOWLEDGE:
        plan.append(
            {
                "tool": "search_knowledge",
                "args": {
                    "query": _canonical_policy_query(domain) if domain else "documentacion odoo",
                    "filters": {"module": domain} if domain and domain != "knowledge" else {},
                    "top_k": 5,
                },
            }
        )

    if route == ERP_DATA and not has_odoo_tool(plan):
        raise RuntimeError("ERP_DATA route requires Odoo tools")
    if route == KNOWLEDGE and not has_knowledge_tool(plan):
        raise RuntimeError("KNOWLEDGE route requires RAG tool")
    if route == MIXED:
        if not has_odoo_tool(plan):
            raise RuntimeError("MIXED route requires Odoo tool")
        if not has_knowledge_tool(plan):
            raise RuntimeError("MIXED route requires RAG tool")
    if route == FALLBACK:
        return []
    return plan
