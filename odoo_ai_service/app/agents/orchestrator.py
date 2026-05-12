from __future__ import annotations

from typing import Any, cast
from time import perf_counter
from uuid import uuid4

from agents.assistant_agent import ask_agent
from app.agents.context_resolver import resolve_context
from app.agents.domain_resolver import DOMAIN_MODEL_MAP, resolve_domain
from app.agents.entity_resolver import resolve_entity
from app.agents.intent_resolver import resolve_intent
from app.agents.normalizer import normalize
from app.agents.plan_builder import build_plan
from app.agents.response_composer import (
    build_odoo_evidence,
    compose_amount_lookup,
    compose_clarification,
    compose_count_result,
    compose_policy_validation,
    compose_ranking_result,
    compose_response,
    compose_status_lookup,
)
from app.agents.route_selector import CLARIFICATION, ERP_DATA, FALLBACK, KNOWLEDGE, MIXED, select_route
from app.agents.tool_executor import execute_plan
from app.agents.types import AgentContext, AgentMetrics, AgentResponse, Entity, KnowledgeResult, ToolExecutionResult
from app.memory.memory_store import load_memory, memory_scope_from_context, persist_memory
from app.memory.schemas import ActiveEntity, ConversationMemory


def _build_metrics(
    *,
    route: str,
    intent: str | None,
    domain: str | None,
    tools_used: list[str],
    memory_hit: bool,
    grounded: bool,
    response_faithful: bool,
    active_model: str | None,
    active_id: int | None,
    memory_updated: bool,
) -> AgentMetrics:
    return {
        "route_selected": route,
        "intent_detected": intent,
        "domain_detected": domain,
        "tools_used": list(tools_used or []),
        "memory_hit": bool(memory_hit),
        "grounded": bool(grounded),
        "response_faithful": bool(response_faithful),
        "active_model": active_model,
        "active_id": active_id,
        "memory_updated": bool(memory_updated),
    }


def _extract_primary_record(execution_result: ToolExecutionResult) -> dict[str, Any] | None:
    results = execution_result.get("results") or []
    for row in results:
        result = row.get("result")
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result[0]
    return None


def _extract_search_ids(execution_result: ToolExecutionResult) -> list[int]:
    results = execution_result.get("results") or []
    for row in results:
        result = row.get("result")
        if isinstance(result, list) and result and all(isinstance(item, int) for item in result):
            return result
    return []


def _extract_knowledge_result(execution_result: ToolExecutionResult) -> KnowledgeResult | None:
    results = execution_result.get("results") or []
    for row in results:
        if row.get("tool") == "search_knowledge" and isinstance(row.get("result"), dict):
            return row["result"]
    return None


def _extract_first_tool_result(execution_result: ToolExecutionResult) -> Any:
    results = execution_result.get("results") or []
    for row in results:
        if "result" in row:
            return row.get("result")
    return None


def _extract_first_record_list(execution_result: ToolExecutionResult) -> Any:
    results = execution_result.get("results") or []
    for row in results:
        result = row.get("result")
        if isinstance(result, list) and result and isinstance(result[0], dict):
            return result
    return _extract_first_tool_result(execution_result)


def _resolve_active_model(primary_record: dict[str, Any] | None, plan_entity: Entity | None, domain: str | None) -> str | None:
    if isinstance(primary_record, dict) and isinstance(primary_record.get("model"), str):
        return primary_record.get("model")
    if isinstance(plan_entity, dict) and isinstance(plan_entity.get("model"), str):
        return plan_entity.get("model")
    if domain and domain in DOMAIN_MODEL_MAP:
        return DOMAIN_MODEL_MAP[domain].get("main_model")
    return None


def _domain_for_model(model: str | None) -> str | None:
    if not isinstance(model, str):
        return None
    for domain_name, config in DOMAIN_MODEL_MAP.items():
        if config.get("main_model") == model:
            return domain_name
    return None


def _entity_type_for_domain(domain: str | None) -> str:
    if domain == "purchase":
        return "purchase_order"
    if domain == "sale":
        return "sale_order"
    if domain == "invoice":
        return "invoice"
    if domain == "inventory":
        return "stock_picking"
    return "active_record"


def _client_active_entity_from_context(context: AgentContext | dict | None) -> ActiveEntity | None:
    if not isinstance(context, dict):
        return None
    client = context.get("client")
    if not isinstance(client, dict):
        return None
    active_model = client.get("active_model")
    active_id = client.get("active_id")
    if isinstance(active_id, str) and active_id.isdigit():
        active_id = int(active_id)
    if not isinstance(active_model, str) or not isinstance(active_id, int) or active_id <= 0:
        return None
    domain = _domain_for_model(active_model)
    if domain not in {"purchase", "sale", "invoice", "inventory"}:
        return None
    return ActiveEntity(
        type=_entity_type_for_domain(domain),
        model=active_model,
        id=active_id,
        name=None,
        confidence=0.92,
    )


def _memory_with_client_active_entity(
    memory: ConversationMemory | None,
    context: AgentContext | dict | None,
    session_id: str,
    user_id: int,
    db_name: str,
) -> ConversationMemory | None:
    if memory and memory.active_entity:
        return memory
    client_entity = _client_active_entity_from_context(context)
    if not client_entity:
        return memory
    base = memory or ConversationMemory(session_id=session_id, user_id=user_id, db_name=db_name)
    base.active_entity = client_entity
    base.active_domain = _domain_for_model(client_entity.model)
    return base


def _safe_result_sample(result: Any) -> Any:
    sensitive_keys = {"password", "token", "secret"}
    if isinstance(result, list):
        return [_safe_result_sample(item) for item in result[:3]]
    if isinstance(result, dict):
        return {
            key: _safe_result_sample(value)
            for key, value in result.items()
            if str(key).lower() not in sensitive_keys
        }
    return result


def _is_evidence_result(result: Any) -> bool:
    return not (isinstance(result, list) and all(isinstance(item, int) for item in result))


def _fallback_response(question: str, context: AgentContext | dict | None, history: list | None) -> dict:
    return ask_agent(question, context=context, history=history)


def _clarification_message(intent: str | None, context_message: str | None = None) -> str:
    if context_message:
        return context_message
    if intent == "line_items":
        return "Necesito contexto: indícame una venta, factura u orden específica para revisar sus productos o líneas."
    if intent == "amount_lookup":
        return "Necesito contexto: indícame la venta, factura u orden específica para consultar el total."
    if intent == "status_lookup":
        return "Necesito contexto: indícame la venta, factura u orden específica para consultar su estado."
    return "Necesito más contexto."


def _memory_from_success(
    session_id: str,
    user_id: int,
    db_name: str,
    existing_memory: ConversationMemory | None,
    route: str,
    intent: str | None,
    domain: str | None,
    question: str,
    trace_id: str,
    tools_used: list[str],
    record: dict[str, Any] | None,
    entity: Entity | None,
    knowledge_result: KnowledgeResult | None,
) -> tuple[dict[str, Any], bool, float]:
    save_started_at = perf_counter()
    base = existing_memory or ConversationMemory(session_id=session_id)
    base.session_id = session_id
    base.user_id = user_id
    base.db_name = db_name
    memory_updated = False

    if record and isinstance(record.get("id"), int):
        entity_type = entity.get("type") if isinstance(entity, dict) and entity.get("type") != "relative_reference" else f"{domain}_entity"
        active_entity = ActiveEntity(
            type=str(entity_type or record.get("name") or "entity"),
            model=str(entity.get("model") if isinstance(entity, dict) and entity.get("model") else record.get("model") or ""),
            id=int(record["id"]),
            name=record.get("name"),
            confidence=float(entity.get("confidence") or 1.0) if isinstance(entity, dict) else 1.0,
        )
        base.active_entity = active_entity
        base.last_fields = {
            key: value
            for key, value in record.items()
            if key in {"amount_total", "currency_id", "state", "partner_id", "name"}
        }
        memory_updated = True

    base.active_domain = domain
    base.last_route = route
    base.last_intent = intent
    base.last_question = question
    base.last_tools_used = list(tools_used or [])
    base.last_sources = [source.get("doc_name") for source in (knowledge_result or {}).get("sources", [])]
    base.metadata = {**(base.metadata or {}), "trace_id": trace_id}

    persist_memory(base, user_id=user_id, db_name=db_name)
    save_latency_ms = round((perf_counter() - save_started_at) * 1000, 2)
    return base.to_context_dict(), memory_updated, save_latency_ms


def ask_hybrid_agent(
    question: str,
    session_id: str | None = None,
    context: AgentContext | dict | None = None,
    history: list | None = None,
) -> AgentResponse:
    started_at = perf_counter()
    base_context = cast(AgentContext, dict(context or {}))
    trace_id = base_context.get("request_id") or str(uuid4())
    base_context["request_id"] = trace_id
    resolved_session_id = session_id or trace_id
    scoped_user_id, scoped_session_id, scoped_db_name = memory_scope_from_context(resolved_session_id, base_context)
    resolved_session_id = scoped_session_id
    normalized_question = normalize(question)

    entity = resolve_entity(normalized_question)
    domain = resolve_domain(normalized_question, entity=entity)
    intent = resolve_intent(normalized_question, domain=domain, entity=entity)

    if (
        intent == "explanation"
        and not isinstance(entity, dict)
        and domain is None
        and any(keyword in normalized_question for keyword in ("politica", "proceso", "manual", "documentacion", "segun"))
    ):
        domain = "knowledge"

    memory_started_at = perf_counter()
    memory = load_memory(resolved_session_id, base_context)
    memory = _memory_with_client_active_entity(
        memory,
        base_context,
        resolved_session_id,
        scoped_user_id,
        scoped_db_name,
    )
    memory_load_ms = round((perf_counter() - memory_started_at) * 1000, 2)
    context_resolution = resolve_context(
        entity,
        memory,
        intent=intent,
        domain=domain,
        question=normalized_question,
    )
    active_entity = context_resolution.get("entity")

    if domain is None and isinstance(active_entity, dict):
        active_model = active_entity.get("model")
        if isinstance(active_model, str):
            domain = next(
                (
                    domain_name
                    for domain_name, config in DOMAIN_MODEL_MAP.items()
                    if config.get("main_model") == active_model
                ),
                domain,
            )

    if intent is None:
        intent = resolve_intent(normalized_question, domain=domain, entity=active_entity or entity)

    route = select_route(
        domain=domain,
        intent=intent,
        entity=active_entity or entity,
        has_relative_reference_without_context=bool(
            context_resolution.get("needs_clarification")
        ),
    )

    if route == CLARIFICATION:
        answer = compose_clarification(_clarification_message(intent, context_resolution.get("clarification_message")))
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        active_model = active_entity.get("model") if isinstance(active_entity, dict) else None
        active_id = active_entity.get("id") if isinstance(active_entity, dict) else None
        metrics = _build_metrics(
            route=route,
            intent=intent,
            domain=domain,
            tools_used=[],
            memory_hit=bool(context_resolution.get("memory_hit")),
            grounded=False,
            response_faithful=True,
            active_model=active_model,
            active_id=active_id,
            memory_updated=False,
        )
        return {
            "answer": answer,
            "route": route,
            "route_selected": route,
            "intent_detected": intent,
            "domain_detected": domain,
            "tools_used": [],
            "sources": [],
            "odoo_evidence": [],
            "latency_ms": latency_ms,
            "tokens_used": 0,
            "trace_id": trace_id,
            "session_id": resolved_session_id,
            "memory": memory.to_context_dict() if memory else {},
            "memory_hit": metrics["memory_hit"],
            "needs_clarification": True,
            "grounded": metrics["grounded"],
            "response_faithful": metrics["response_faithful"],
            "active_model": metrics["active_model"],
            "active_id": metrics["active_id"],
            "memory_updated": False,
            "answer_mode": route,
            "metrics": metrics,
        }

    plan_entity = active_entity or entity
    base_context["session_id"] = resolved_session_id
    base_context["route"] = route
    base_context["route_selected"] = route
    base_context["intent"] = intent
    base_context["intent_detected"] = intent
    base_context["domain"] = domain
    base_context["domain_detected"] = domain
    try:
        plan = build_plan(route, domain, intent, plan_entity, question=normalized_question)
    except RuntimeError as exc:
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        active_model = active_entity.get("model") if isinstance(active_entity, dict) else None
        active_id = active_entity.get("id") if isinstance(active_entity, dict) else None
        metrics = _build_metrics(
            route=FALLBACK,
            intent=intent,
            domain=domain,
            tools_used=[],
            memory_hit=bool(context_resolution.get("memory_hit")),
            grounded=False,
            response_faithful=False,
            active_model=active_model,
            active_id=active_id,
            memory_updated=False,
        )
        return {
            "answer": str(exc),
            "route": FALLBACK,
            "route_selected": FALLBACK,
            "intent_detected": intent,
            "domain_detected": domain,
            "tools_used": [],
            "sources": [],
            "odoo_evidence": [],
            "latency_ms": latency_ms,
            "tokens_used": 0,
            "trace_id": trace_id,
            "session_id": resolved_session_id,
            "memory": memory.to_context_dict() if memory else {},
            "memory_hit": metrics["memory_hit"],
            "needs_clarification": False,
            "grounded": metrics["grounded"],
            "response_faithful": metrics["response_faithful"],
            "active_model": metrics["active_model"],
            "active_id": metrics["active_id"],
            "memory_updated": False,
            "answer_mode": FALLBACK,
            "error": str(exc),
            "metrics": metrics,
        }

    if route == FALLBACK:
        legacy = _fallback_response(question, base_context, history)
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        legacy_needs_clarification = bool(legacy.get("needs_clarification")) or legacy.get("answer_mode") == "clarification_required"
        response_route = CLARIFICATION if legacy_needs_clarification else FALLBACK
        metrics = _build_metrics(
            route=response_route,
            intent=intent,
            domain=domain,
            tools_used=(legacy.get("metadata") or {}).get("tools_used") or [],
            memory_hit=bool(context_resolution.get("memory_hit")),
            grounded=False,
            response_faithful=False,
            active_model=None,
            active_id=None,
            memory_updated=False,
        )
        return {
            "answer": legacy.get("answer"),
            "route": response_route,
            "route_selected": response_route,
            "intent_detected": intent,
            "domain_detected": domain,
            "tools_used": metrics["tools_used"],
            "sources": [],
            "odoo_evidence": [],
            "latency_ms": latency_ms,
            "tokens_used": ((legacy.get("metadata") or {}).get("tokens_input") or 0) + ((legacy.get("metadata") or {}).get("tokens_output") or 0),
            "trace_id": trace_id,
            "session_id": resolved_session_id,
            "memory": legacy.get("memory") or {},
            "memory_hit": metrics["memory_hit"],
            "needs_clarification": legacy_needs_clarification,
            "grounded": metrics["grounded"],
            "response_faithful": metrics["response_faithful"],
            "active_model": metrics["active_model"],
            "active_id": metrics["active_id"],
            "memory_updated": False,
            "answer_mode": legacy.get("answer_mode"),
            "erp_result": legacy,
            "metrics": metrics,
        }

    execution_result = execute_plan(plan, entity=plan_entity, context=base_context)
    tools_used = execution_result.get("tools_used") or []
    knowledge_result = _extract_knowledge_result(execution_result)
    primary_record = _extract_primary_record(execution_result)
    search_ids = _extract_search_ids(execution_result)

    if primary_record is None and search_ids and isinstance(plan_entity, dict):
        primary_record = {
            "id": search_ids[0],
            "name": plan_entity.get("code"),
        }

    if route == ERP_DATA and not execution_result.get("success"):
        answer = execution_result.get("message") or "No pude ejecutar la consulta ERP."
        grounded = False
        response_faithful = False
    elif route == ERP_DATA and intent == "amount_lookup" and primary_record:
        answer = compose_amount_lookup(primary_record, domain=domain)
        grounded = True
        response_faithful = True
    elif route == ERP_DATA and intent == "status_lookup" and primary_record:
        answer = compose_status_lookup(primary_record, domain=domain)
        grounded = True
        response_faithful = True
    elif route == ERP_DATA and intent == "count":
        answer = compose_count_result(_extract_first_tool_result(execution_result), domain=domain)
        grounded = True
        response_faithful = True
    elif route == ERP_DATA and intent == "ranking":
        answer = compose_ranking_result(_extract_first_record_list(execution_result), domain=domain)
        grounded = True
        response_faithful = True
    elif route == KNOWLEDGE:
        answer = compose_response(route=route, knowledge_result=knowledge_result)
        grounded = bool((knowledge_result or {}).get("sources"))
        response_faithful = grounded
    elif route == MIXED:
        answer = compose_policy_validation(primary_record, knowledge_result, domain=domain)
        grounded = bool(primary_record) and bool((knowledge_result or {}).get("sources"))
        response_faithful = grounded
    else:
        answer = execution_result.get("message") or "No pude resolver la consulta."
        grounded = False
        response_faithful = False

    response_memory, memory_updated, memory_save_ms = _memory_from_success(
        session_id=resolved_session_id,
        user_id=scoped_user_id,
        db_name=scoped_db_name,
        existing_memory=memory,
        route=route,
        intent=intent,
        domain=domain,
        question=normalized_question,
        trace_id=trace_id,
        tools_used=tools_used,
        record=primary_record if grounded or route == ERP_DATA else None,
        entity=plan_entity,
        knowledge_result=knowledge_result,
    )

    latency_ms = round((perf_counter() - started_at) * 1000, 2)
    tokens_used = int((knowledge_result or {}).get("tokens_used") or 0)
    tool_trace = execution_result.get("tool_trace") or []
    tool_latencies = {
        str(row.get("tool")): row.get("latency_ms")
        for row in tool_trace
        if isinstance(row, dict) and row.get("tool")
    }
    observability = {
        "tool_trace": tool_trace,
        "tool_latencies": tool_latencies,
        "memory_latency_ms": {
            "load": memory_load_ms,
            "save": memory_save_ms,
        },
        "rag_latency_ms": {
            "total": (knowledge_result or {}).get("latency_ms"),
            "retrieval": (knowledge_result or {}).get("retrieval_ms"),
            "llm": (knowledge_result or {}).get("llm_ms"),
        } if knowledge_result else {},
    }
    odoo_evidence = [
        {
            "tool": row.get("tool"),
            "model": (row.get("args") or {}).get("model"),
            "domain": (row.get("args") or {}).get("domain"),
            "fields": (row.get("args") or {}).get("fields"),
            "result_sample": _safe_result_sample(row.get("result")),
        }
        for row in (execution_result.get("results") or [])
        if str(row.get("tool", "")).startswith("query_odoo_") and _is_evidence_result(row.get("result"))
    ]
    active_model = _resolve_active_model(primary_record, plan_entity, domain)
    active_id = primary_record.get("id") if isinstance(primary_record, dict) else None
    metrics = _build_metrics(
        route=route,
        intent=intent,
        domain=domain,
        tools_used=tools_used,
        memory_hit=bool(context_resolution.get("memory_hit")),
        grounded=grounded,
        response_faithful=response_faithful,
        active_model=active_model,
        active_id=active_id,
        memory_updated=memory_updated,
    )

    return {
        "answer": answer,
        "route": route,
        "route_selected": route,
        "intent_detected": intent,
        "domain_detected": domain,
        "tools_used": tools_used,
        "sources": (knowledge_result or {}).get("sources") or [],
        "odoo_evidence": odoo_evidence or build_odoo_evidence(None),
        "latency_ms": latency_ms,
        "tokens_used": tokens_used,
        "trace_id": trace_id,
        "session_id": resolved_session_id,
        "memory": response_memory,
        "memory_hit": metrics["memory_hit"],
        "needs_clarification": False,
        "grounded": metrics["grounded"],
        "response_faithful": metrics["response_faithful"],
        "active_model": metrics["active_model"],
        "active_id": metrics["active_id"],
        "memory_updated": metrics["memory_updated"],
        "answer_mode": route,
        "partial_failure": bool(execution_result.get("partial_failure")),
        "error_type": execution_result.get("error_type"),
        "observability": observability,
        "metadata": observability,
        "metrics": metrics,
        "erp_result": {
            "success": execution_result.get("success"),
            "results": execution_result.get("results"),
            "message": execution_result.get("message"),
        },
    }
