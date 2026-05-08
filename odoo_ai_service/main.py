import logging
import hmac
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.agents.orchestrator import ask_hybrid_agent
from app.api.schemas import AskRequest, KnowledgeQueryRequest
from app.core.config import get_settings
from app.knowledge.ingest_service import get_ingest_service
from app.observability import emit_event
from app.tools.search_knowledge import search_knowledge
from schemas.chat_schema import Question
from agents.assistant_agent import ask_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odoo_ai_service")
settings = get_settings()


def _dump_model(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _ask_v1_log_payload(result: dict) -> dict:
    metrics = result.get("metrics") or {}
    return {
        "trace_id": result.get("trace_id"),
        "session_id": result.get("session_id"),
        "route_selected": result.get("route_selected", metrics.get("route_selected")),
        "intent_detected": result.get("intent_detected", metrics.get("intent_detected")),
        "domain_detected": result.get("domain_detected", metrics.get("domain_detected")),
        "tools_used": result.get("tools_used", metrics.get("tools_used")),
        "memory_hit": result.get("memory_hit", metrics.get("memory_hit")),
        "grounded": result.get("grounded", metrics.get("grounded")),
        "response_faithful": result.get("response_faithful", metrics.get("response_faithful")),
        "active_model": result.get("active_model", metrics.get("active_model")),
        "active_id": result.get("active_id", metrics.get("active_id")),
        "memory_updated": result.get("memory_updated", metrics.get("memory_updated")),
        "needs_clarification": result.get("needs_clarification"),
        "partial_failure": result.get("partial_failure"),
        "error_type": result.get("error_type"),
        "latency_ms": result.get("latency_ms"),
        "tokens_used": result.get("tokens_used"),
    }

app = FastAPI(title=settings.app_name, version=settings.app_version)
PROTECTED_PATHS = {
    "/ask",
    "/v1/ask",
    "/v1/ingest",
    "/v1/knowledge/query",
}


def _is_protected_path(path: str) -> bool:
    return path in PROTECTED_PATHS


def _is_valid_service_token(provided: str | None) -> bool:
    expected = settings.ai_service_api_key
    if not expected:
        return False
    return bool(provided) and hmac.compare_digest(str(provided), str(expected))


if hasattr(app, "middleware"):
    @app.middleware("http")
    async def require_ai_service_token(request, call_next):
        if not settings.ai_service_auth_required or not _is_protected_path(request.url.path):
            return await call_next(request)

        provided = (
            request.headers.get("X-AI-Service-Token")
            or request.headers.get("X-AI-Token")
            or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        )
        if not settings.ai_service_api_key:
            logger.error("AI service auth misconfigured: missing AI_SERVICE_API_KEY/ODOO_AI_TOKEN")
            return JSONResponse(
                status_code=503,
                content={"error_code": "ERR_AUTH_NOT_CONFIGURED", "error": "Servicio IA no configurado para autenticación."},
            )
        if not _is_valid_service_token(provided):
            return JSONResponse(status_code=401, content={"error_code": "ERR_UNAUTHORIZED", "error": "No autorizado."})

        return await call_next(request)

@app.post("/ask")
def ask(q: Question):
    context = q.context or {}
    request_id = context.get("request_id") if isinstance(context, dict) else None
    emit_event(logger, "LEGACY_REQUEST_START", trace_id=request_id, endpoint="/ask", question_length=len(q.question or ""), has_history=bool(q.history))
    result = ask_agent(q.question, context=q.context, history=q.history)
    emit_event(
        logger,
        "LEGACY_REQUEST_END",
        trace_id=result.get("request_id"),
        endpoint="/ask",
        answer_mode=result.get("answer_mode"),
        error_code=result.get("error_code"),
        latency_ms=(result.get("metadata") or {}).get("latency_ms"),
    )

    return result


@app.get("/v1/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "knowledge_enabled": settings.enable_knowledge,
    }


@app.post("/v1/knowledge/query")
def knowledge_query(payload: KnowledgeQueryRequest):
    result = search_knowledge(
        query=payload.query,
        module=payload.module,
        doc_id=payload.doc_id,
        top_k=payload.top_k or settings.top_k,
    )
    return result


@app.post("/v1/ingest")
async def ingest(module: str | None = Form(default=None), files: list[UploadFile] = File(...)):
    service = get_ingest_service()
    file_payloads = []
    for upload in files:
        file_payloads.append((upload.filename or "unknown", await upload.read()))
    result = service.ingest_files(file_payloads, module=module)
    return _dump_model(result)


@app.post("/v1/ask")
def ask_v1(payload: AskRequest):
    request_id = (payload.context or {}).get("request_id")
    emit_event(
        logger,
        "REQUEST_START",
        trace_id=request_id,
        endpoint="/v1/ask",
        session_id=payload.session_id,
        question_length=len(payload.question or ""),
        has_history=bool(payload.history),
    )
    try:
        result = ask_hybrid_agent(
            question=payload.question,
            session_id=payload.session_id,
            context=payload.context,
            history=payload.history,
        )
        log_payload = _ask_v1_log_payload(result)
        emit_event(
            logger,
            "ROUTE_SELECTED",
            trace_id=log_payload.get("trace_id"),
            route_selected=log_payload.get("route_selected"),
            intent_detected=log_payload.get("intent_detected"),
            domain_detected=log_payload.get("domain_detected"),
            tools_used=log_payload.get("tools_used"),
        )
        emit_event(logger, "REQUEST_END", endpoint="/v1/ask", **log_payload)
        return result
    except Exception as exc:
        logger.exception("V1_ASK_ERROR")
        emit_event(
            logger,
            "REQUEST_ERROR",
            trace_id=request_id,
            endpoint="/v1/ask",
            session_id=payload.session_id,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={
                "answer": "No pude resolver la consulta híbrida en este momento.",
                "route": "error",
                "tools_used": [],
                "sources": [],
                "odoo_evidence": [],
                "latency_ms": None,
                "tokens_used": None,
                "trace_id": (payload.context or {}).get("request_id"),
                "error": str(exc),
            },
        )
