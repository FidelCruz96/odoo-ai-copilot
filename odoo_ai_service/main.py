import logging
import json
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.agents.orchestrator import ask_hybrid_agent
from app.api.schemas import AskRequest, KnowledgeQueryRequest
from app.core.config import get_settings
from app.knowledge.ingest_service import get_ingest_service
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

@app.post("/ask")
def ask(q: Question):
    context = q.context or {}
    request_id = context.get("request_id") if isinstance(context, dict) else None
    logger.info(
        "ASK_START %s",
        json.dumps(
            {
                "request_id": request_id,
                "question": q.question,
                "has_history": bool(q.history),
            },
            ensure_ascii=False,
        ),
    )
    result = ask_agent(q.question, context=q.context, history=q.history)
    logger.info(
        "ASK_END %s",
        json.dumps(
            {
                "request_id": result.get("request_id"),
                "answer_mode": result.get("answer_mode"),
                "error_code": result.get("error_code"),
                "latency_ms": (result.get("metadata") or {}).get("latency_ms"),
            },
            ensure_ascii=False,
        ),
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
    logger.info(
        "V1_ASK_START %s",
        json.dumps(
            {
                "request_id": (payload.context or {}).get("request_id"),
                "session_id": payload.session_id,
                "question": payload.question,
                "has_history": bool(payload.history),
            },
            ensure_ascii=False,
        ),
    )
    try:
        result = ask_hybrid_agent(
            question=payload.question,
            session_id=payload.session_id,
            context=payload.context,
            history=payload.history,
        )
        logger.info("V1_ASK_END %s", json.dumps(_ask_v1_log_payload(result), ensure_ascii=False))
        return result
    except Exception as exc:
        logger.exception("V1_ASK_ERROR")
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
