import importlib
import sys
import types
import unittest
from unittest.mock import patch


def _install_dependency_stubs():
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
            if "default" in kwargs:
                return kwargs["default"]
            return default

        pydantic_stub.BaseModel = BaseModel
        pydantic_stub.Field = Field
        sys.modules["pydantic"] = pydantic_stub

    if "fastapi" not in sys.modules:
        fastapi_stub = types.ModuleType("fastapi")
        fastapi_responses_stub = types.ModuleType("fastapi.responses")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = []

            def post(self, path):
                def decorator(fn):
                    self.routes.append(("POST", path, fn.__name__))
                    return fn

                return decorator

            def get(self, path):
                def decorator(fn):
                    self.routes.append(("GET", path, fn.__name__))
                    return fn

                return decorator

        class UploadFile:
            def __init__(self, filename=None, content=b""):
                self.filename = filename
                self._content = content

            async def read(self):
                return self._content

        class JSONResponse:
            def __init__(self, status_code=200, content=None):
                self.status_code = status_code
                self.content = content

        def File(*args, **kwargs):
            return None

        def Form(default=None, **kwargs):
            return default

        fastapi_stub.FastAPI = FastAPI
        fastapi_stub.File = File
        fastapi_stub.Form = Form
        fastapi_stub.UploadFile = UploadFile
        fastapi_responses_stub.JSONResponse = JSONResponse
        sys.modules["fastapi"] = fastapi_stub
        sys.modules["fastapi.responses"] = fastapi_responses_stub

    if "psycopg2" not in sys.modules:
        psycopg2_stub = types.ModuleType("psycopg2")
        psycopg2_extras_stub = types.ModuleType("psycopg2.extras")

        def connect(*args, **kwargs):
            raise RuntimeError("psycopg2 stub should not be used in unit tests")

        class RealDictCursor:
            pass

        def execute_batch(*args, **kwargs):
            return None

        psycopg2_stub.connect = connect
        psycopg2_extras_stub.RealDictCursor = RealDictCursor
        psycopg2_extras_stub.execute_batch = execute_batch
        psycopg2_stub.extras = psycopg2_extras_stub
        sys.modules["psycopg2"] = psycopg2_stub
        sys.modules["psycopg2.extras"] = psycopg2_extras_stub

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


_install_dependency_stubs()
main = importlib.import_module("main")


class TestV1Contract(unittest.TestCase):
    def test_health_contract(self):
        result = main.health()
        self.assertEqual(result["status"], "ok")
        self.assertIn("service", result)
        self.assertIn("version", result)

    def test_knowledge_query_delegates_to_tool(self):
        payload = main.KnowledgeQueryRequest(
            query="que es un picking",
            module="stock",
            doc_id="doc-1",
            top_k=3,
        )
        with patch.object(main, "search_knowledge", return_value={"answer": "ok", "sources": []}) as search:
            result = main.knowledge_query(payload)

        self.assertEqual(result["answer"], "ok")
        search.assert_called_once_with(
            query="que es un picking",
            module="stock",
            doc_id="doc-1",
            top_k=3,
        )

    def test_ask_v1_success_contract(self):
        payload = main.AskRequest(
            question="Top clientes por facturacion este mes",
            session_id="abc123",
            context={"company_id": 1},
            history=[],
        )
        mocked = {
            "answer": "1. Cliente A",
            "route": "erp_data",
            "route_selected": "erp_data",
            "intent_detected": "ranking",
            "domain_detected": "sale",
            "tools_used": ["query_odoo_group"],
            "sources": [],
            "odoo_evidence": [],
            "latency_ms": 120.0,
            "tokens_used": 15,
            "trace_id": "trace-1",
            "session_id": "abc123",
            "memory_hit": False,
            "grounded": True,
            "response_faithful": True,
            "active_model": "sale.order",
            "active_id": 77,
            "memory_updated": True,
            "partial_failure": False,
            "error_type": None,
            "needs_clarification": False,
            "metrics": {
                "route_selected": "erp_data",
                "intent_detected": "ranking",
                "domain_detected": "sale",
                "tools_used": ["query_odoo_group"],
                "memory_hit": False,
                "grounded": True,
                "response_faithful": True,
                "active_model": "sale.order",
                "active_id": 77,
                "memory_updated": True,
            },
        }
        with patch.object(main, "ask_hybrid_agent", return_value=mocked) as ask_hybrid:
            result = main.ask_v1(payload)

        self.assertEqual(result["route"], "erp_data")
        self.assertEqual(result["trace_id"], "trace-1")
        self.assertEqual(result["metrics"]["active_id"], 77)
        ask_hybrid.assert_called_once_with(
            question="Top clientes por facturacion este mes",
            session_id="abc123",
            context={"company_id": 1},
            history=[],
        )

    def test_ask_v1_error_contract(self):
        payload = main.AskRequest(
            question="Explícame el flujo de compras",
            session_id="abc123",
            context={"request_id": "req-77"},
            history=[],
        )
        with patch.object(main, "ask_hybrid_agent", side_effect=RuntimeError("boom")):
            result = main.ask_v1(payload)

        self.assertEqual(result.status_code, 503)
        self.assertEqual(result.content["route"], "error")
        self.assertEqual(result.content["trace_id"], "req-77")
        self.assertEqual(result.content["error"], "boom")


if __name__ == "__main__":
    unittest.main()
