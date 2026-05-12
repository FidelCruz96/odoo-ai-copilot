# Security

## Scope

Odoo AI Copilot is designed as a read-only assistant for ERP data. The AI Service plans tool calls, but Odoo executes ORM queries under the requesting user's access context.

## Controls

- Internal service token between Odoo and the AI Service.
- Read-only Odoo operations: `search`, `search_read`, `read`, `read_group`, `search_count`.
- Allowlist of models and blocklist of sensitive fields.
- Access context with `uid`, companies, groups hash, language, timezone, and database name.
- Conversation memory scoped by `db_name + user_id + session_id`.
- Persistent audit log for tool calls in Odoo.
- Evidence sanitization before responses and logs.
- Optional RBAC enforcement with `AI_ENFORCE_RBAC=true`.
- Basic per-user/session rate limiting through `AI_RATE_LIMIT_PER_MINUTE`.

## Threat Model

| Risk | Mitigation |
| --- | --- |
| Prompt injection in RAG documents | Treat RAG as evidence only; keep ERP actions read-only and tool-planned. |
| Sensitive field exfiltration | Field blocklist in AI Service and Odoo bridge; audit payload sanitization. |
| Cross-user memory leakage | Memory scope includes database, user, and session. |
| Cross-company data access | Odoo ORM executes with user and allowed company context. |
| Unauthorized AI Service calls | Shared service token required by default. |
| Logs containing secrets | Structured log redaction and small result samples only. |
| Excessive usage | Optional rate limit per user/session. |

## Reporting

Do not open public issues with credentials, tokens, database dumps, or customer data. Rotate any exposed token immediately and report privately to the repository owner.
