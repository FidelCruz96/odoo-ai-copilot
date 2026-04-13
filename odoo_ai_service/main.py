import logging
from fastapi import FastAPI
from schemas.chat_schema import Question
from agents.assistant_agent import ask_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("odoo_ai_service")

app = FastAPI()

@app.post("/ask")
def ask(q: Question):
    logger.info("ask question=%s", q.question)
    result = ask_agent(q.question, context=q.context, history=q.history)
    logger.info("ask answer=%s", result.get("answer"))

    return result
