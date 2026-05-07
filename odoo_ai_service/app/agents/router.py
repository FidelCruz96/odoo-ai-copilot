from __future__ import annotations


DOCUMENTATION_KEYWORDS = [
    "qué es",
    "que es",
    "cómo funciona",
    "como funciona",
    "proceso",
    "política",
    "politica",
    "regla",
    "manual",
    "documentación",
    "documentacion",
    "según",
    "segun",
    "explica",
]

ERP_KEYWORDS = [
    "ventas",
    "facturas",
    "compras",
    "clientes",
    "productos",
    "órdenes",
    "ordenes",
    "cotizaciones",
    "pendientes",
    "top",
    "total",
    "monto",
]

MIXED_KEYWORDS = [
    "debió",
    "debio",
    "debería",
    "deberia",
    "según la política",
    "segun la politica",
    "según el proceso",
    "segun el proceso",
    "cumple",
    "por qué",
    "por que",
]


class HybridRoute:
    DOCUMENTATION = "documentation"
    ERP_DATA = "erp_data"
    MIXED = "mixed"
    CLARIFICATION = "clarification"


def classify_route(question: str, memory: dict | None = None) -> str:
    q = (question or "").strip().lower()
    if not q:
        return HybridRoute.CLARIFICATION
    if _needs_clarification(q, memory):
        return HybridRoute.CLARIFICATION
    if any(keyword in q for keyword in MIXED_KEYWORDS):
        return HybridRoute.MIXED
    has_doc = any(keyword in q for keyword in DOCUMENTATION_KEYWORDS)
    has_erp = any(keyword in q for keyword in ERP_KEYWORDS)
    if has_doc and has_erp:
        return HybridRoute.MIXED
    if has_doc:
        return HybridRoute.DOCUMENTATION
    if has_erp:
        return HybridRoute.ERP_DATA
    if isinstance(memory, dict) and memory.get("last_entity"):
        return HybridRoute.MIXED if "según" in q or "segun" in q else HybridRoute.ERP_DATA
    return HybridRoute.CLARIFICATION


def _needs_clarification(question: str, memory: dict | None = None) -> bool:
    if any(keyword in question for keyword in ("facturas pendientes", "compras pendientes", "ventas pendientes")):
        return False
    if "pendientes" in question and not any(keyword in question for keyword in ("factura", "compra", "venta", "picking")):
        return True
    if question in {"pendientes", "total", "detalle"}:
        return True
    return False
