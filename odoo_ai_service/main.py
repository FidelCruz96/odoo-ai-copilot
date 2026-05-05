import logging
import json
from fastapi import FastAPI
from schemas.chat_schema import Question
from agents.assistant_agent import ask_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odoo_ai_service")

app = FastAPI()

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
