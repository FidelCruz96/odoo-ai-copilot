from typing import Any, Optional
from pydantic import BaseModel


class Question(BaseModel):
    question: str
    context: Optional[dict[str, Any]] = None
    history: Optional[list[dict[str, Any]]] = None
