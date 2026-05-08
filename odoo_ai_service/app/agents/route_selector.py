from __future__ import annotations

from app.agents.types import Entity, RouteName


ERP_DATA = "erp_data"
KNOWLEDGE = "knowledge"
MIXED = "mixed"
CLARIFICATION = "clarification"
FALLBACK = "fallback"


def select_route(
    domain: str | None,
    intent: str | None,
    entity: Entity | None,
    has_relative_reference_without_context: bool,
) -> RouteName:
    if has_relative_reference_without_context:
        return CLARIFICATION

    if intent in {"amount_lookup", "status_lookup", "line_items"} and not entity:
        return CLARIFICATION

    if intent in ["amount_lookup", "status_lookup", "count", "ranking", "line_items"]:
        return ERP_DATA

    if intent == "explanation" and domain in ["knowledge", "purchase", "sale", "invoice", "inventory"]:
        return KNOWLEDGE

    if intent == "policy_validation":
        return MIXED

    if domain in ["purchase", "sale", "invoice"] and intent == "policy_validation":
        return MIXED

    return FALLBACK
