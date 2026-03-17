import json
import logging
import os
from openai import RateLimitError, APIError, APIConnectionError
from llm.llm_client import call_llm
from tools.odoo_get_tool import query_odoo, get_schema
from tools.tool_definitions import tools
from datetime import date, timedelta

today = date.today()

logger = logging.getLogger(__name__)

DEFAULT_MAX_HISTORY = int(os.getenv("AI_CHAT_HISTORY_LIMIT", "8"))

TOOL_MAP = {
    "get_schema": lambda **kwargs: get_schema(**kwargs),
    "query_odoo_search": lambda **kwargs: query_odoo(operation="search",**{**kwargs, "limit": kwargs.get("limit", 20)}
    ),
    "query_odoo_read": lambda **kwargs: query_odoo(operation="read", **kwargs),
    "query_odoo_group": lambda **kwargs: query_odoo(operation="read_group",**{**kwargs, "limit": kwargs.get("limit", 20)}
    ),
}

def _build_system_prompt() -> str:
    today = date.today()
    year  = today.year
    month = today.month

    # Este mes
    month_start = today.replace(day=1)
    month_end   = today.replace(month=month % 12 + 1, day=1) - timedelta(days=1) \
                  if month < 12 else today.replace(day=31)

    # Esta semana (lunes → domingo)
    week_start = today - timedelta(days=today.weekday())
    week_end   = week_start + timedelta(days=6)

    # Últimos 3 meses
    m3 = month - 3 if month > 3 else month - 3 + 12
    y3 = year      if month > 3 else year - 1
    last_3m_start = today.replace(year=y3, month=m3, day=1)

    # Este año
    year_start = today.replace(month=1,  day=1)
    year_end   = today.replace(month=12, day=31)

    return f"""Hoy: {today} | este_mes: {month_start}/{month_end} | semana: {week_start}/{week_end} | 3meses: {last_3m_start}/{today} | año: {year_start}/{year_end}

    Eres asistente Odoo. Usa tools, nunca inventes datos.
    Usa get_schema() para conocer modelos y campos disponibles antes de consultar si hay dudas.
    Tools: get_schema() | query_odoo_search(IDs) | query_odoo_read(campos) | query_odoo_group(agregaciones)
    Flujo: listas→search(limit=10)+read | top/total/sum/count/avg→group(limit=10)
    Dominios: [campo, operador, valor] EXACTAMENTE 3 elementos. Operadores: = != > >= < <= like ilike in not in
    Modelos: res.partner | ventas: sale.order | lineas venta: sale.order.line | product.product | account.move | compras: purchase.order | lineas compra: purchase.order.line
    Clientes: customer_rank > 0 | Proveedores: supplier_rank > 0

    Interpretación:
    ventas => sale.order (cliente)
    compras empresa => purchase.order (proveedor)
    cliente que más compras hizo => sale.order + groupby partner_id + partner_id_count desc
    más ventas/compras => amount_total desc
    más órdenes/cantidad => __count desc
    productos más vendidos => sale.order.line + groupby product_id + suma product_uom_qty desc
    productos más comprados => purchase.order.line + groupby product_id + suma product_qty desc
    si ambigüo => pregunta

    group orderby válido: amount_total desc | partner_id_count desc | __count desc | product_uom_qty desc | product_qty desc
    NO uses: "count field desc" ni "count DESC" (inválidos en Odoo).
    Si una tool falla, cambia el argumento que falló; no repitas la misma llamada."""


# ── Validador de dominios Odoo ─────────────────────────────────────────────────

def _validate_domain(domain: list) -> list:
    """
    Valida que cada cláusula del dominio tenga exactamente 3 elementos
    y un operador reconocido. Lanza ValueError si detecta algo inválido,
    para que el loop devuelva el error al LLM y pueda autocorregirse.
    """
    VALID_OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "like", "ilike", "in", "not in", "child_of"}
    LOGICAL_OPS     = {"&", "|", "!"}
    validated = []

    for clause in domain:
        # Operadores lógicos: válidos tal cual
        if isinstance(clause, str) and clause in LOGICAL_OPS:
            validated.append(clause)
            continue

        if not isinstance(clause, (list, tuple)) or len(clause) != 3:
            raise ValueError(
                f"Cláusula de dominio inválida: {clause}. "
                f"Se esperan EXACTAMENTE 3 elementos (field, operator, value), "
                f"se recibieron {len(clause) if isinstance(clause, (list, tuple)) else type(clause)}."
            )

        field, operator, value = clause

        if operator not in VALID_OPERATORS:
            raise ValueError(
                f"Operador inválido '{operator}' en {clause}. "
                f"Operadores válidos: {sorted(VALID_OPERATORS)}"
            )

        validated.append([field, operator, value])

    return validated

def _compress_tool_result(tool_name: str, result) -> str:
    """Reduce el tamaño del resultado antes de meterlo al contexto."""
    MAX_ITEMS = 10

    if isinstance(result, list):
        truncated = result[:MAX_ITEMS]
        suffix = f"\n[...{len(result) - MAX_ITEMS} más omitidos]" if len(result) > MAX_ITEMS else ""

        if tool_name == "query_odoo_search":
            # Solo IDs, no hace falta más
            return f"IDs encontrados: {truncated}{suffix}"

        if tool_name == "query_odoo_read":
            # Quitar campos internos verbosos de Odoo
            cleaned = []
            for item in truncated:
                cleaned.append({
                    k: v for k, v in item.items()
                    if not k.startswith("__") and k != "write_uid"
                })
            return json.dumps(cleaned, ensure_ascii=False) + suffix

        if tool_name == "query_odoo_group":
            cleaned = []
            for item in truncated:
                # Quitar __domain y __context que Odoo añade y no aportan
                cleaned.append({
                    k: v for k, v in item.items()
                    if k not in ("__domain", "__context", "__fold")
                })
            return json.dumps(cleaned, ensure_ascii=False) + suffix

    if isinstance(result, dict) and "error" in result:
        return f"ERROR: {result['error']}"

    if isinstance(result, dict) and tool_name == "get_schema":
        model_count = len(result.keys()) if isinstance(result, dict) else 0
        sample = list(result.keys())[:10]
        return json.dumps({"models": model_count, "sample": sample}, ensure_ascii=False)

    return str(result)[:500]  # fallback con límite duro

# ── Validador contra schema ───────────────────────────────────────────────────

def _field_names_from_domain(domain):
    names = []
    if not isinstance(domain, list):
        return names
    for clause in domain:
        if isinstance(clause, (list, tuple)) and len(clause) == 3:
            names.append(clause[0])
    return names


def _validate_against_schema(schema, model, fields=None, groupby=None, domain=None):
    if not isinstance(schema, dict) or not model:
        return None

    model_info = schema.get(model)
    if not model_info:
        return f"Modelo '{model}' no existe en el schema."

    model_fields = model_info.get("fields") or {}
    invalid = []

    if fields:
        for f in fields:
            if f not in model_fields:
                invalid.append(f)

    if groupby:
        for f in groupby:
            if f not in model_fields:
                invalid.append(f)

    if domain:
        for f in _field_names_from_domain(domain):
            if f not in model_fields:
                invalid.append(f)

    if invalid:
        unique = sorted(set(invalid))
        return f"Campos inválidos en {model}: {unique}"

    return None


# ── Agente principal ───────────────────────────────────────────────────────────

def ask_agent(question: str, context: dict | None = None, history: list | None = None, max_iterations: int = 10) -> str:
    messages = [
        {"role": "system", "content": _build_system_prompt()},
    ]
    if context:
        try:
            ctx_json = json.dumps(context, ensure_ascii=False)
        except Exception:
            ctx_json = str(context)
        messages.append({"role": "system", "content": f"Contexto funcional: {ctx_json}"})
    combined_history = []
    if context and isinstance(context, dict):
        server_hist = context.get("history_server")
        if isinstance(server_hist, list):
            combined_history.extend(server_hist)
    if history and isinstance(history, list):
        combined_history.extend(history)
    if combined_history:
        ctx_limit = None
        if context and isinstance(context, dict):
            try:
                ctx_limit = int(context.get("history_limit"))
            except Exception:
                ctx_limit = None
        limit = ctx_limit if ctx_limit is not None else DEFAULT_MAX_HISTORY
        if limit < 0:
            limit = 0
        if context and isinstance(context, dict) and context.get("use_server_history") is False:
            combined_history = [h for h in combined_history if h.get("source") != "server"]
        selected = combined_history[-limit:] if limit else []
        for item in selected:
            role = item.get("role")
            text = item.get("text") or ""
            if role == "user":
                messages.append({"role": "user", "content": text})
            elif role in ("bot", "assistant"):
                messages.append({"role": "assistant", "content": text})
    messages.append({"role": "user",   "content": question})

    schema_cache = None

    for iteration in range(max_iterations):
        logger.info(f"Iteración {iteration + 1}/{max_iterations}")

        # ── Llamada al LLM ──────────────────────────────────────────────────
        try:
            response = call_llm(messages, tools)
        except RateLimitError:
            return ("El servicio de IA está temporalmente saturado por límite de "
                    "tokens. Intenta nuevamente en unos segundos.")
        except (APIError, APIConnectionError):
            return "No pude conectar con el servicio de IA. Intenta nuevamente."
        except Exception:
            return "Ocurrió un error inesperado en el servicio de IA."

        message = response.choices[0].message
        logger.info(f"LLM RESPONSE: {message}")

        # ── Sin tool_calls → respuesta final ───────────────────────────────
        if not message.tool_calls:
            return message.content or "No se obtuvo respuesta."

        # ── Con tool_calls → ejecutar TODAS las herramientas del turno ─────
        messages.append(message)  # el asistente pidió herramientas

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            logger.info(f"TOOL CALL: {tool_name}")

            # Herramienta desconocida
            if tool_name not in TOOL_MAP:
                tool_result = f"Error: herramienta '{tool_name}' no encontrada."
                logger.warning(tool_result)

            else:
                try:
                    arguments = json.loads(tool_call.function.arguments)

                    # Validar dominio antes de ejecutar en Odoo
                    if "domain" in arguments:
                        arguments["domain"] = _validate_domain(arguments["domain"])

                    # Validación contra schema para queries Odoo
                    if tool_name in ("query_odoo_search", "query_odoo_read", "query_odoo_group"):
                        if schema_cache is None:
                            schema_cache = get_schema()
                        validation_error = _validate_against_schema(
                            schema_cache,
                            arguments.get("model"),
                            fields=arguments.get("fields"),
                            groupby=arguments.get("groupby"),
                            domain=arguments.get("domain"),
                        )
                        if validation_error:
                            tool_result = f"Error de schema: {validation_error}"
                            logger.error(tool_result)
                            raise ValueError(validation_error)

                    tool_result = TOOL_MAP[tool_name](**arguments)
                    logger.info(f"Resultado '{tool_name}': {str(tool_result)[:300]}")

                except json.JSONDecodeError as e:
                    tool_result = f"Error: argumentos JSON inválidos: {e}"
                    logger.error(tool_result)
                except ValueError as e:
                    # Error de validación de dominio → LLM puede autocorregirse
                    tool_result = f"Error de validación: {e}"
                    logger.error(tool_result)
                except Exception as e:
                    tool_result = f"Error ejecutando herramienta '{tool_name}': {e}"
                    logger.error(tool_result)

            messages.append({
                "role":        "tool",
                "tool_call_id": tool_call.id,
                "content":     _compress_tool_result(tool_name, tool_result),
    })

    # Seguridad: no debería llegar aquí en condiciones normales
    logger.error(f"El agente agotó {max_iterations} iteraciones sin respuesta final.")
    return "No pude completar la consulta tras varios intentos. Intenta reformular la pregunta."
