# Observability and Audit

## Request Trace

Each `/v1/ask` request carries a `trace_id` through route selection, tool execution, memory access, RAG, and response composition.

Standard fields:

- `trace_id`
- `session_id`
- `db_name`
- `user_id`
- `route_selected`
- `intent_detected`
- `domain_detected`
- `tools_used`
- `latency_ms`
- `tokens_used`
- `error_type`

## Tool Trace

The AI Service records per-tool latency, result size, success state, and RAG-specific timing. Odoo persists the executed ORM query summary in `ai.tool.audit.log`.

## Memory Trace

Memory load/save events include backend, scope, hit status, latency, and error type. Memory contents are not logged.

## Audit Boundary

The AI Service traces planning decisions. Odoo persists the execution audit because Odoo owns ORM access control and company/user scope.
