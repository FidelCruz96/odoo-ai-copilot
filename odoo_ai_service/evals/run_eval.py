from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_DATASET = Path(__file__).resolve().parent / "datasets" / "orchestrator_smoke.jsonl"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL: {exc}") from exc
            if not isinstance(item, dict) or not item.get("id") or not item.get("question"):
                raise ValueError(f"{path}:{line_number}: each case requires id and question")
            cases.append(item)
    return cases


def _tools_match(actual: list[str], expected: list[str]) -> bool:
    return list(actual or []) == list(expected or [])


def _models_from_response(response: dict[str, Any]) -> set[str]:
    models: set[str] = set()
    active_model = response.get("active_model")
    if isinstance(active_model, str):
        models.add(active_model)
    for row in response.get("odoo_evidence") or []:
        if isinstance(row, dict) and isinstance(row.get("model"), str):
            models.add(row["model"])
    erp_result = response.get("erp_result") if isinstance(response.get("erp_result"), dict) else {}
    for row in erp_result.get("results") or []:
        args = row.get("args") if isinstance(row, dict) else {}
        if isinstance(args, dict) and isinstance(args.get("model"), str):
            models.add(args["model"])
    return models


def evaluate_case(case: dict[str, Any], response: dict[str, Any], *, enforce_latency: bool = False) -> dict[str, Any]:
    failures: list[str] = []
    warnings: list[str] = []
    expected_route = case.get("expected_route")
    expected_intent = case.get("expected_intent")
    expected_tools = case.get("expected_tools")
    expected_model = case.get("expected_model")

    actual_route = response.get("route_selected") or response.get("route")
    actual_tools = response.get("tools_used") or []

    if expected_route is not None and actual_route != expected_route:
        failures.append(f"route expected={expected_route!r} actual={actual_route!r}")
    if expected_intent is not None and response.get("intent_detected") != expected_intent:
        failures.append(f"intent expected={expected_intent!r} actual={response.get('intent_detected')!r}")
    if expected_tools is not None and not _tools_match(actual_tools, expected_tools):
        failures.append(f"tools expected={expected_tools!r} actual={actual_tools!r}")
    if expected_model is not None and expected_model not in _models_from_response(response):
        failures.append(f"model expected={expected_model!r} actual={sorted(_models_from_response(response))!r}")
    if "grounded" in case and bool(response.get("grounded")) != bool(case["grounded"]):
        failures.append(f"grounded expected={case['grounded']!r} actual={response.get('grounded')!r}")
    if "response_faithful" in case and bool(response.get("response_faithful")) != bool(case["response_faithful"]):
        failures.append(f"response_faithful expected={case['response_faithful']!r} actual={response.get('response_faithful')!r}")
    if "needs_clarification" in case and bool(response.get("needs_clarification")) != bool(case["needs_clarification"]):
        failures.append(f"needs_clarification expected={case['needs_clarification']!r} actual={response.get('needs_clarification')!r}")
    if case.get("max_latency_ms") is not None:
        latency = response.get("latency_ms")
        if not isinstance(latency, (int, float)) or latency > float(case["max_latency_ms"]):
            message = f"latency expected<={case['max_latency_ms']} actual={latency!r}"
            if enforce_latency:
                failures.append(message)
            else:
                warnings.append(message)
    for expected_text in case.get("answer_contains") or []:
        if str(expected_text).lower() not in str(response.get("answer") or "").lower():
            failures.append(f"answer missing {expected_text!r}")

    return {
        "id": case["id"],
        "question": case["question"],
        "ok": not failures,
        "failures": failures,
        "warnings": warnings,
        "route": actual_route,
        "intent": response.get("intent_detected"),
        "tools": actual_tools,
        "latency_ms": response.get("latency_ms"),
        "tokens_used": response.get("tokens_used"),
        "grounded": response.get("grounded"),
        "response_faithful": response.get("response_faithful"),
        "error_type": response.get("error_type") or response.get("error_code"),
    }


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 2)


def summarize_results(results: list[dict[str, Any]], duration_ms: float) -> dict[str, Any]:
    latencies = [float(item["latency_ms"]) for item in results if isinstance(item.get("latency_ms"), (int, float))]
    token_values = [int(item["tokens_used"]) for item in results if isinstance(item.get("tokens_used"), int)]
    tools = Counter(tool for item in results for tool in (item.get("tools") or []))
    routes = Counter(str(item.get("route")) for item in results if item.get("route"))
    intents = Counter(str(item.get("intent")) for item in results if item.get("intent"))
    error_types = Counter(
        str(item.get("error_type") or failure.split(":", 1)[0])
        for item in results
        if not item.get("ok")
        for failure in (item.get("failures") or ["unknown_error"])
    )
    passed = sum(1 for item in results if item.get("ok"))
    failed = len(results) - passed
    latency_warnings = [
        warning
        for item in results
        for warning in (item.get("warnings") or [])
        if str(warning).startswith("latency ")
    ]

    return {
        "pass_rate": round((passed / len(results)) * 100, 2) if results else 0.0,
        "duration_ms": round(duration_ms, 2),
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "tokens": {
            "total": sum(token_values),
            "avg": round(sum(token_values) / len(token_values), 2) if token_values else 0.0,
        },
        "routes": dict(sorted(routes.items())),
        "intents": dict(sorted(intents.items())),
        "tools": dict(sorted(tools.items())),
        "error_types": dict(sorted(error_types.items())),
        "latency_warning_count": len(latency_warnings),
        "failed_case_ids": [item["id"] for item in results if not item.get("ok")],
        "passed": passed,
        "failed": failed,
    }


def _default_context(uid: int | None, company_id: int | None, request_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"request_id": request_id}
    if uid:
        company_ids = [company_id] if company_id else []
        context["security"] = {
            "uid": uid,
            "user_id": uid,
            "company_id": company_id,
            "active_company_id": company_id,
            "company_ids": company_ids,
            "allowed_company_ids": company_ids,
        }
        context["access_context"] = dict(context["security"])
        context["user"] = {"id": uid}
        context["company"] = {"id": company_id}
    db_name = os.getenv("AI_EVAL_DB_NAME") or os.getenv("EVAL_ODOO_DB") or os.getenv("ODOO_DB")
    if db_name:
        context["db_name"] = db_name
        if "security" in context:
            context["security"]["db_name"] = db_name
        if "access_context" in context:
            context["access_context"]["db_name"] = db_name
    return context


def call_http(url: str, token: str | None, case: dict[str, Any], uid: int | None, company_id: int | None) -> dict[str, Any]:
    request_id = f"eval-{case['id']}"
    context = _default_context(uid, company_id, request_id)
    context.update(case.get("context") or {})
    payload = {
        "question": case["question"],
        "session_id": case.get("session_id") or request_id,
        "context": context,
        "history": case.get("history") or [],
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-AI-Service-Token"] = token
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=case.get("timeout_seconds", 30)) as response:
        return json.loads(response.read().decode("utf-8"))


def run_eval(args: argparse.Namespace) -> dict[str, Any]:
    dataset = load_jsonl(Path(args.dataset))
    if args.dry_run:
        return {
            "ok": True,
            "mode": "dry_run",
            "cases": len(dataset),
            "passed": len(dataset),
            "failed": 0,
            "duration_ms": 0.0,
            "summary": {
                "dataset_valid": True,
                "case_ids": [case["id"] for case in dataset],
            },
            "results": [],
        }

    results = []
    started = time.perf_counter()
    for case in dataset:
        try:
            response = call_http(args.url, args.token, case, args.uid, args.company_id)
            result = evaluate_case(case, response, enforce_latency=args.enforce_latency)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            result = {
                "id": case["id"],
                "question": case["question"],
                "ok": False,
                "failures": [f"request_error: {exc}"],
            }
        results.append(result)

    passed = sum(1 for item in results if item["ok"])
    failed = len(results) - passed
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    summary = summarize_results(results, duration_ms)
    return {
        "ok": failed == 0,
        "cases": len(results),
        "passed": passed,
        "failed": failed,
        "duration_ms": duration_ms,
        "summary": summary,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Odoo AI Copilot orchestrator evals.")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--url", default=os.getenv("AI_EVAL_URL", "http://localhost:8001/v1/ask"))
    parser.add_argument("--token", default=os.getenv("AI_SERVICE_TOKEN") or os.getenv("ODOO_AI_TOKEN"))
    parser.add_argument("--uid", type=int, default=int(os.getenv("AI_EVAL_UID", "2")))
    parser.add_argument("--company-id", type=int, default=int(os.getenv("AI_EVAL_COMPANY_ID", "1")))
    parser.add_argument("--dry-run", action="store_true", help="Only validate the dataset format.")
    parser.add_argument(
        "--enforce-latency",
        action="store_true",
        default=_env_bool("EVAL_ENFORCE_LATENCY", default=False),
        help="Fail cases that exceed max_latency_ms. By default latency is reported as a warning.",
    )
    parser.add_argument("--report", help="Optional JSON report output path.")
    args = parser.parse_args(argv)

    report = run_eval(args)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    print(text)
    if args.report:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
