from __future__ import annotations


def format_currency(amount, currency_value) -> str:
    try:
        value = float(amount or 0.0)
    except Exception:
        value = 0.0
    currency_name = None
    if isinstance(currency_value, (list, tuple)) and len(currency_value) >= 2:
        currency_name = currency_value[1]
    elif isinstance(currency_value, str):
        currency_name = currency_value
    symbol = "S/" if currency_name == "PEN" else currency_name or ""
    if symbol:
        return f"{symbol} {value:,.2f}"
    return f"{value:,.2f}"


def build_odoo_evidence(erp_result: dict | None) -> list[dict]:
    metadata = (erp_result or {}).get("metadata") or {}
    traces = metadata.get("tool_trace") or []
    answer = (erp_result or {}).get("answer") or ""
    evidence = []
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        evidence.append(
            {
                "tool": trace.get("tool"),
                "model": trace.get("model"),
                "domain": trace.get("domain"),
                "fields": trace.get("fields"),
                "result": answer[:400],
            }
        )
    return evidence


def compose_clarification(message: str) -> str:
    return message


def compose_amount_lookup(record: dict, domain: str | None = None) -> str:
    label = "El registro"
    if domain == "purchase" or (record.get("name") or "").upper().startswith("PO"):
        label = "La compra"
    elif domain == "sale" or (record.get("name") or "").upper().startswith("SO"):
        label = "La venta"
    elif domain == "invoice":
        label = "La factura"
    amount_label = format_currency(record.get("amount_total"), record.get("currency_id"))
    return f"{label} {record.get('name')} tiene un monto total de {amount_label}."


def _extract_threshold_from_knowledge(knowledge_result: dict | None) -> float | None:
    text = ((knowledge_result or {}).get("answer") or "").replace(",", "")
    for token in text.split():
        stripped = token.replace("s/", "").replace("S/", "").strip(" .:")
        try:
            value = float(stripped)
        except Exception:
            continue
        if value >= 1000:
            return value
    return None


def compose_policy_validation(record: dict | None, knowledge_result: dict | None, domain: str | None = None) -> str:
    sources = (knowledge_result or {}).get("sources") or []
    knowledge_answer = (knowledge_result or {}).get("answer") or "No encontré suficiente contexto documental para responder con precisión."
    if not record:
        return (
            f"{knowledge_answer}\n\n"
            "No pude validar la orden exacta en Odoo con el identificador proporcionado. "
            "Si me compartes el número real de la orden, la cruzo con la política."
        )

    threshold = _extract_threshold_from_knowledge(knowledge_result)
    amount_total = record.get("amount_total")
    currency_label = format_currency(amount_total, record.get("currency_id"))
    if threshold is not None and isinstance(amount_total, (int, float)):
        expected = float(amount_total) > threshold
        verdict = "Sí" if expected else "No"
        reason = "supera" if expected else "no supera"
        threshold_text = f"S/ {threshold:,.2f}"
        source_label = sources[0].get("doc_name") if sources else "la documentación recuperada"
        return (
            f"{verdict}, según {source_label}.\n\n"
            f"Evidencia Odoo: {record.get('name')} tiene un monto de {currency_label} y estado {record.get('state')}.\n"
            f"Evidencia documental: la política indica un umbral de aprobación de {threshold_text}.\n"
            f"Conclusión: el monto {reason} el umbral documentado."
        )
    return (
        f"Evidencia Odoo: {record.get('name')} tiene un monto de {currency_label} y estado {record.get('state')}.\n"
        f"Evidencia documental: {knowledge_answer}"
    )


def compose_response(route: str, knowledge_result: dict | None = None, erp_result: dict | None = None) -> str:
    if route == "documentation":
        return (knowledge_result or {}).get("answer") or "No encontré respuesta documental."
    if route == "erp_data":
        return (erp_result or {}).get("answer") or "No encontré evidencia en Odoo."

    knowledge_answer = (knowledge_result or {}).get("answer") or "Sin evidencia documental suficiente."
    erp_answer = (erp_result or {}).get("answer") or "Sin evidencia operativa suficiente."
    sources = (knowledge_result or {}).get("sources") or []
    odoo_evidence = build_odoo_evidence(erp_result)
    not_found = any(
        token in erp_answer.lower()
        for token in (
            "no he podido encontrar",
            "no encontr",
            "no existe",
        )
    )

    direct_answer = erp_answer
    if route == "mixed" and sources and not_found:
        direct_answer = (
            f"{knowledge_answer}\n\n"
            "No pude validar la orden exacta en Odoo con el identificador proporcionado. "
            "Si me compartes el nombre real de la compra o un identificador existente, la cruzo con la política."
        )

    lines = [
        "Respuesta directa:",
        direct_answer,
        "",
        "Evidencia de Odoo:",
    ]
    if odoo_evidence:
        for item in odoo_evidence[:3]:
            lines.append(f"- Modelo consultado: {item.get('model') or 'N/D'}")
            lines.append(f"- Dominio: {item.get('domain') or []}")
            lines.append(f"- Campos: {item.get('fields') or []}")
            lines.append(f"- Resultado: {item.get('result') or 'Sin detalle'}")
    else:
        lines.append("- Sin evidencia ORM estructurada disponible en esta respuesta.")

    lines.extend(["", "Fuentes documentales:"])
    if sources:
        for source in sources[:5]:
            lines.append(
                f"- Documento: {source.get('doc_name')} | Score: {source.get('score')} | Página: {source.get('page')}"
            )
    else:
        lines.append("- Sin fuentes documentales recuperadas.")

    lines.extend(["", "Conclusión:", knowledge_answer])
    return "\n".join(lines)
