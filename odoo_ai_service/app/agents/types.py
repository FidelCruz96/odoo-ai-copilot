from __future__ import annotations

from typing import Any, Literal, TypedDict


RouteName = Literal["erp_data", "knowledge", "mixed", "clarification", "fallback"]
IntentName = Literal["amount_lookup", "status_lookup", "count", "ranking", "line_items", "policy_validation", "explanation"]
DomainName = Literal["purchase", "sale", "invoice", "inventory", "product", "partner", "knowledge"]


class Entity(TypedDict, total=False):
    type: str
    model: str | None
    id: int
    code: str
    name: str
    display_name: str
    text: str
    target_domain: DomainName | str | None
    lookup_field: str
    confidence: float
    explicit_code: bool
    fields: dict[str, Any]


class AccessContext(TypedDict, total=False):
    uid: int
    user_id: int
    company_id: int | None
    active_company_id: int | None
    company_ids: list[int]
    allowed_company_ids: list[int]
    groups: list[str]
    groups_hash: str | None
    lang: str | None
    tz: str | None
    request_id: str


class AgentContext(TypedDict, total=False):
    request_id: str
    user: dict[str, Any]
    company: dict[str, Any]
    security: AccessContext
    access_context: AccessContext
    client: dict[str, Any]
    memory: dict[str, Any]
    history_limit: int
    use_server_history: bool
    history_server: list[dict[str, Any]]
    lang: str | None
    tz: str | None


class ContextResolution(TypedDict, total=False):
    entity: Entity | None
    memory_hit: bool
    needs_clarification: bool
    clarification_message: str


class ToolArguments(TypedDict, total=False):
    model: str
    operation: str
    domain: list[Any]
    fields: list[str]
    ids: list[int] | str
    groupby: list[str]
    orderby: str
    limit: int
    query: str
    filters: dict[str, Any]
    top_k: int
    context: AgentContext | dict[str, Any]


class ToolStep(TypedDict):
    tool: str
    args: ToolArguments


class ToolExecutionRow(TypedDict, total=False):
    tool: str
    args: ToolArguments
    result: Any
    latency_ms: float


class ToolTraceRow(TypedDict, total=False):
    tool: str | None
    model: str | None
    operation: str | None
    latency_ms: float
    result_size: int | None
    success: bool
    error_type: str | None
    retrieval_ms: float | None
    llm_ms: float | None
    sources_count: int
    tokens_used: int | None


class ToolExecutionResult(TypedDict, total=False):
    success: bool
    tools_used: list[str]
    results: list[ToolExecutionRow]
    tool_trace: list[ToolTraceRow]
    partial_failure: bool
    error_type: str | None
    message: str | None
    trace_id: str


class KnowledgeSource(TypedDict, total=False):
    doc_name: str
    score: float
    doc_id: str
    module: str
    chunk_id: str


class KnowledgeResult(TypedDict, total=False):
    answer: str
    sources: list[KnowledgeSource]
    tokens_used: int
    latency_ms: float
    retrieval_ms: float
    llm_ms: float
    raw_chunks: int
    filtered_chunks: int


class OdooEvidence(TypedDict, total=False):
    tool: str | None
    model: str | None
    domain: list[Any] | None
    fields: list[str] | None
    result: str
    result_sample: Any


class AgentMetrics(TypedDict):
    route_selected: str
    intent_detected: str | None
    domain_detected: str | None
    tools_used: list[str]
    memory_hit: bool
    grounded: bool
    response_faithful: bool
    active_model: str | None
    active_id: int | None
    memory_updated: bool


class AgentResponse(TypedDict, total=False):
    answer: str | None
    route: str
    route_selected: str
    intent_detected: str | None
    domain_detected: str | None
    tools_used: list[str]
    sources: list[dict[str, Any]]
    odoo_evidence: list[OdooEvidence]
    latency_ms: float | None
    tokens_used: int | None
    trace_id: str
    session_id: str
    memory: dict[str, Any]
    memory_hit: bool
    needs_clarification: bool
    grounded: bool
    response_faithful: bool
    active_model: str | None
    active_id: int | None
    memory_updated: bool
    answer_mode: str | None
    partial_failure: bool
    error_type: str | None
    error: str
    metrics: AgentMetrics
    erp_result: dict[str, Any]
