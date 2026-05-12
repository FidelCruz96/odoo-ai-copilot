# ADR 0001: Use a Deterministic Orchestrator

## Status

Accepted

## Context

Free-form LLM responses are not reliable enough for ERP questions that require model, domain, intent, permissions, and evidence.

## Decision

Use a deterministic orchestrator before any generative step. The system normalizes the question, resolves entity/domain/intent, selects a route, builds a tool plan, executes read-only tools, and composes grounded responses.

## Consequences

- More predictable behavior for ERP data.
- Easier evals and audit.
- More code than a simple chatbot, but lower operational risk.
