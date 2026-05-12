from __future__ import annotations

import re
import unicodedata

from .intent_catalog import INTENT_CATALOG

INTENT_PRIORITY = [
    "top_ventas_por_monto",
    "top_compras_por_monto",
    "top_facturas_por_monto",
    "top_clientes_ventas_mes",
    "clientes_facturas_vencidas_ranking",
    "ordenes_compra_pendientes_recepcion",
    "pickings_pendientes_validar_hoy",
    "resumen_operativo_hoy",
    "ordenes_venta_pendientes_facturar",
    "count_pickings_por_estado",
    "list_ultimas_ventas_con_factura",
    "list_ultimas_compras_con_factura",
    "facturas_vencidas_count",
    "list_facturas_pendientes",
    "count_facturas_pendientes",
    "list_facturas_emitidas_periodo",
    "producto_mas_vendido_por_monto",
    "producto_mas_vendido_por_cantidad",
    "promedio_ventas_por_cliente_periodo",
    "top_proveedor_por_unidades",
    "top_proveedor_por_compras",
    "top_vendedor_por_pedidos",
    "top_vendedor_por_monto",
    "top_cliente_por_monto",
    "count_productos_activos",
    "count_ordenes_venta_periodo",
    "count_clientes",
]


def normalize_text(text: str) -> str:
    text = text or ""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def contains_any(text: str, options: list[str]) -> bool:
    return any(opt in text for opt in options)


def detect_intent_by_keywords(question: str) -> str | None:
    q = normalize_text(question)

    if (
        contains_any(q, ["picking", "pickings"])
        and contains_any(q, ["cuantos", "cuántos", "cantidad", "conteo", "total"])
        and contains_any(q, ["espera", "en espera", "waiting"])
        and contains_any(q, ["disponible", "disponibles", "asignado", "asignados"])
        and contains_any(q, ["hecho", "hechos", "done", "completado", "completados"])
    ):
        return "count_pickings_por_estado"

    if "resumen operativo" in q and ("hoy" in q or "dia" in q or "día" in q):
        return "resumen_operativo_hoy"

    if (
        contains_any(q, ["pickings", "picking"])
        and contains_any(q, ["pendiente", "pendientes", "por validar"])
        and contains_any(q, ["validar", "validacion", "validación"])
        and "hoy" in q
    ):
        return "pickings_pendientes_validar_hoy"

    if (
        contains_any(q, ["orden de compra", "ordenes de compra", "órdenes de compra", "compra", "compras"])
        and contains_any(q, ["pendiente", "pendientes", "recepcion", "recepción", "por recibir"])
    ):
        return "ordenes_compra_pendientes_recepcion"

    if (
        contains_any(q, ["pedido de venta", "pedidos de venta", "orden de venta", "ordenes de venta", "órdenes de venta", "venta", "ventas"])
        and contains_any(q, ["pendiente", "pendientes"])
        and contains_any(q, ["facturar", "por facturar"])
    ):
        return "ordenes_venta_pendientes_facturar"

    if (
        "cliente" in q
        and "factura" in q
        and contains_any(q, ["vencida", "vencidas", "atrasada", "atrasadas"])
        and contains_any(q, ["mas", "más", "top"])
    ):
        return "clientes_facturas_vencidas_ranking"

    if (
        "cliente" in q
        and contains_any(q, ["venta", "ventas"])
        and contains_any(q, ["mas", "más", "top"])
        and contains_any(q, ["mes", "este mes", "mes actual"])
    ):
        return "top_clientes_ventas_mes"

    if (
        contains_any(q, ["ultimo", "ultimos", "ultima", "ultimas", "reciente", "recientes"])
        and contains_any(q, ["venta", "ventas", "pedido", "pedidos", "orden de venta", "ordenes de venta"])
        and contains_any(q, ["factura", "facturas", "comprobante", "comprobantes"])
    ):
        return "list_ultimas_ventas_con_factura"

    if (
        contains_any(q, ["ultimo", "ultimos", "ultima", "ultimas", "reciente", "recientes"])
        and contains_any(q, ["compra", "compras", "proveedor", "proveedores", "orden de compra", "ordenes de compra"])
        and contains_any(q, ["factura", "facturas", "comprobante", "comprobantes"])
    ):
        return "list_ultimas_compras_con_factura"

    if (
        "factura" in q
        and contains_any(q, ["pendiente", "no pagada", "no pagadas", "por cobrar", "sin pagar", "abierta", "abiertas"])
        and contains_any(q, ["muestra", "muestrame", "muestreme", "lista", "listar", "detalle", "ver", "dame"])
    ):
        return "list_facturas_pendientes"

    if (
        "factura" in q
        and contains_any(q, ["emitida", "emitidas", "publicada", "publicadas"])
        and contains_any(q, ["muestra", "muestrame", "muestreme", "lista", "listar", "detalle", "ver", "dame"])
    ):
        return "list_facturas_emitidas_periodo"

    if (
        "factura" in q
        and contains_any(q, ["pendiente", "no pagada", "no pagadas", "por cobrar", "sin pagar", "abierta", "abiertas"])
    ):
        return "count_facturas_pendientes"

    if (
        "factura" in q
        and contains_any(q, ["vencida", "vencidas", "atrasada", "atrasadas", "fuera de fecha"])
    ):
        return "facturas_vencidas_count"

    if (
        contains_any(q, ["producto", "productos", "articulo", "articulos", "item", "items"])
        and "activo" in q
        and contains_any(q, ["cuantos", "cuantas", "numero", "cantidad", "total"])
    ):
        return "count_productos_activos"

    if (
        contains_any(q, ["orden de venta", "ordenes de venta", "ordenes", "órdenes de venta", "pedido", "pedidos"])
        and contains_any(q, ["cuantos", "cuantas", "numero", "cantidad", "total"])
    ):
        return "count_ordenes_venta_periodo"

    if (
        contains_any(q, ["vendedor", "comercial"])
        and contains_any(q, ["pedido", "pedidos", "orden", "ordenes", "órdenes"])
        and contains_any(q, ["mas", "top", "mejor"])
    ):
        return "top_vendedor_por_pedidos"

    if (
        contains_any(q, ["vendedor", "comercial"])
        and contains_any(q, ["vendio", "vendio mas", "ventas", "facturo", "facturacion", "facturación", "monto", "importe"])
        and contains_any(q, ["mas", "top", "mejor"])
    ):
        return "top_vendedor_por_monto"

    if (
        "cliente" in q
        and contains_any(q, ["compro", "compras", "facturo", "facturacion", "facturacion", "monto"])
        and contains_any(q, ["mas", "top", "mejor"])
    ):
        return "top_cliente_por_monto"

    if (
        "cliente" in q
        and contains_any(q, ["promedio", "media"])
        and contains_any(q, ["venta", "ventas", "facturacion", "facturacion", "compra", "compras"])
    ):
        return "promedio_ventas_por_cliente_periodo"

    if (
        contains_any(q, ["venta", "ventas", "pedido de venta", "pedidos de venta", "orden de venta", "ordenes de venta"])
        and contains_any(q, ["top", "mayor", "mayores", "mas alta", "más alta", "mas altas", "más altas"])
        and not contains_any(q, ["cliente", "clientes", "vendedor", "vendedores", "producto", "productos"])
    ):
        return "top_ventas_por_monto"

    if (
        contains_any(q, ["compra", "compras", "orden de compra", "ordenes de compra"])
        and contains_any(q, ["top", "mayor", "mayores", "mas alta", "más alta", "mas altas", "más altas"])
        and not contains_any(q, ["proveedor", "proveedores", "producto", "productos"])
    ):
        return "top_compras_por_monto"

    if (
        contains_any(q, ["factura", "facturas", "facturacion", "facturación"])
        and contains_any(q, ["top", "mayor", "mayores", "mas alta", "más alta", "mas altas", "más altas"])
        and not contains_any(q, ["cliente", "clientes", "proveedor", "proveedores"])
    ):
        return "top_facturas_por_monto"

    if (
        contains_any(q, ["producto", "productos", "articulo", "articulos", "item", "items"])
        and contains_any(q, ["facturo", "genero mas ventas", "genero mas dinero", "mayor facturacion", "mas ingresos", "monto"])
    ):
        return "producto_mas_vendido_por_monto"

    if (
        contains_any(q, ["producto", "productos", "articulo", "articulos", "item", "items", "cosa"])
        and contains_any(q, ["mas vendido", "se vendio mas", "mas salida", "salio mas", "mas unidades"])
    ):
        return "producto_mas_vendido_por_cantidad"

    if (
        "proveedor" in q
        and contains_any(q, ["unidad", "unidades", "cantidad", "volumen"])
        and contains_any(q, ["mas", "top", "mejor"])
    ):
        return "top_proveedor_por_unidades"

    if (
        "proveedor" in q
        and contains_any(q, ["compras", "compramos", "nos vendio", "nos vendio", "monto", "facturacion", "facturacion", "importe"])
        and contains_any(q, ["mas", "top", "mejor", "principal"])
    ):
        return "top_proveedor_por_compras"

    if (
        contains_any(q, ["venta", "ventas", "facturacion", "facturación"])
        and contains_any(q, ["total", "totales", "acumulado", "suma"])
    ):
        return "ventas_total_periodo"

    return None


def detect_catalog_intent(question: str) -> tuple[str | None, float]:
    q = normalize_text(question)

    for intent_name in INTENT_PRIORITY:
        spec = INTENT_CATALOG.get(intent_name)
        if not spec:
            continue
        for synonym in spec.synonyms:
            if normalize_text(synonym) in q:
                return intent_name, 0.95

    for intent_name, spec in INTENT_CATALOG.items():
        for synonym in spec.synonyms:
            if normalize_text(synonym) in q:
                return intent_name, 0.90

    kw_intent = detect_intent_by_keywords(q)
    if kw_intent:
        return kw_intent, 0.80

    return None, 0.0


def detect_intent_family(question: str) -> str:
    q = (question or "").lower()

    ventas_keywords = ["venta", "ventas", "pedido", "pedidos", "vendedor", "cotización", "cotizaciones"]
    compras_keywords = [
        "compra",
        "compras",
        "proveedor",
        "proveedores",
        "orden de compra",
        "ordenes de compra",
        "órdenes de compra",
    ]
    fact_keywords = ["factura", "facturas", "vencida", "vencidas", "cobro", "cobros", "pago", "pagadas", "pendientes"]
    cliente_keywords = ["cliente", "clientes", "partner", "partners"]
    producto_keywords = ["producto", "productos", "artículo", "articulos", "ítem", "items"]
    inventario_keywords = ["stock", "inventario", "existencias", "almacen", "almacén", "picking", "pickings", "recepcion", "recepción"]

    if any(k in q for k in fact_keywords):
        return "facturacion"
    if any(k in q for k in producto_keywords):
        return "productos"
    if any(k in q for k in compras_keywords):
        return "compras"
    if any(k in q for k in cliente_keywords):
        return "clientes"
    if any(k in q for k in ventas_keywords):
        return "ventas"
    if any(k in q for k in inventario_keywords):
        return "inventario"
    return "general"


def detect_intent(question: str) -> str | None:
    if not question:
        return None
    q = question.lower()

    if any(x in q for x in ["promedio", "promedio de", "media", "average", "avg"]):
        if "cliente" in q or "clientes" in q:
            return "avg_group:partner_id"
        if "vendedor" in q or "vendedores" in q or "usuario" in q:
            return "avg_group:user_id"
        if "proveedor" in q or "proveedores" in q:
            return "avg_group:partner_id"
        if "producto" in q or "productos" in q:
            return "avg_group:product_id"

    if any(k in q for k in ("monto", "importe", "total", "cuanto", "cuánto")) and any(
        k in q for k in ("cada uno", "cada", "esos", "esos clientes", "los mismos", "anteriores")
    ):
        return "amount_followup"

    if any(k in q for k in ("cuantos", "cuántos", "cantidad", "numero", "número", "total")):
        return "count"

    if any(k in q for k in (
        "cuantos", "cuántos", "cantidad", "numero", "número", "total",
        "monto", "importe", "ventas", "compras", "lista", "top", "más", "mas"
    )):
        return "data"

    return None
