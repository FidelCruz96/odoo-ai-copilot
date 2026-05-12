import json
import sys
import types
import unittest
from unittest.mock import patch


if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def dict(self):
            return dict(self.__dict__)

        def model_dump(self):
            return dict(self.__dict__)

    def Field(default=None, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default", default)

    pydantic_stub.BaseModel = BaseModel
    pydantic_stub.Field = Field
    sys.modules["pydantic"] = pydantic_stub

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class DummyOpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai_stub.OpenAI = DummyOpenAI
    openai_stub.RateLimitError = Exception
    openai_stub.APIError = Exception
    openai_stub.APIConnectionError = Exception
    sys.modules["openai"] = openai_stub

if "psycopg2" not in sys.modules:
    psycopg2_stub = types.ModuleType("psycopg2")
    psycopg2_extras_stub = types.ModuleType("psycopg2.extras")
    psycopg2_stub.connect = lambda *args, **kwargs: None
    psycopg2_extras_stub.RealDictCursor = object
    psycopg2_extras_stub.execute_batch = lambda *args, **kwargs: None
    psycopg2_stub.extras = psycopg2_extras_stub
    sys.modules["psycopg2"] = psycopg2_stub
    sys.modules["psycopg2.extras"] = psycopg2_extras_stub


from app.core.config import Settings
from app.knowledge.rag_service import RagService
from app.knowledge.schemas import QueryRequest


class DummyEmbeddingService:
    def embed_query(self, query):
        return [0.1, 0.2]


class DummyVectorService:
    def search(self, query_embedding, top_k, filters):
        return [
            {"doc_id": "1", "doc_name": "purchase_approvals.md", "page": 1, "score": 0.63, "content": "Compras > 10000 requieren aprobación."},
            {"doc_id": "2", "doc_name": "purchase_policy.md", "page": 2, "score": 0.41, "content": "Otra política."},
        ]


class DummyChatCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        message = types.SimpleNamespace(content="Respuesta breve con evidencia.")
        choice = types.SimpleNamespace(message=message)
        usage = types.SimpleNamespace(total_tokens=42)
        return types.SimpleNamespace(choices=[choice], usage=usage)


class DummyOpenAIClient:
    def __init__(self):
        self.chat = types.SimpleNamespace(completions=DummyChatCompletions())


class TestRagLogging(unittest.TestCase):
    def test_rag_query_end_logs_top_score_and_raw_scores(self):
        settings = Settings(
            openai_api_key=None,
            similarity_threshold=0.5,
            top_k=5,
        )
        service = RagService(
            settings=settings,
            embedding_service=DummyEmbeddingService(),
            vector_service=DummyVectorService(),
            client=None,
        )

        with patch("app.knowledge.rag_service.logger.info") as logger_info:
            response = service.answer_query(
                QueryRequest(
                    query="politica aprobacion compras monto umbral orden de compra",
                    filters={"module": "purchase"},
                    top_k=5,
                )
            )

        self.assertEqual(len(response.sources), 1)
        end_calls = [call for call in logger_info.call_args_list if call.args and call.args[0] == "RAG_QUERY_END %s"]
        self.assertTrue(end_calls)
        payload = json.loads(end_calls[-1].args[1])
        self.assertEqual(payload["raw_chunks"], 2)
        self.assertEqual(payload["filtered_chunks"], 1)
        self.assertEqual(payload["top_score"], 0.63)
        self.assertEqual(payload["raw_scores"], [0.63, 0.41])

    def test_rag_llm_prompt_limits_context_and_completion_tokens(self):
        client = DummyOpenAIClient()
        settings = Settings(
            openai_api_key="test-key",
            rag_context_chunks=2,
            rag_context_chars=20,
            rag_max_completion_tokens=123,
        )
        service = RagService(
            settings=settings,
            embedding_service=DummyEmbeddingService(),
            vector_service=DummyVectorService(),
            client=client,
        )
        chunks = [
            {"doc_name": "a.md", "page": 1, "score": 0.9, "content": "A" * 80},
            {"doc_name": "b.md", "page": 2, "score": 0.8, "content": "B" * 80},
            {"doc_name": "c.md", "page": 3, "score": 0.7, "content": "C" * 80},
        ]

        result = service._generate_answer("pregunta", chunks)

        kwargs = client.chat.completions.kwargs
        user_content = kwargs["messages"][1]["content"]
        self.assertEqual(result["tokens_used"], 42)
        self.assertEqual(kwargs["max_completion_tokens"], 123)
        self.assertIn("A" * 20, user_content)
        self.assertIn("B" * 20, user_content)
        self.assertNotIn("C" * 20, user_content)
        self.assertNotIn("A" * 21, user_content)


if __name__ == "__main__":
    unittest.main()
