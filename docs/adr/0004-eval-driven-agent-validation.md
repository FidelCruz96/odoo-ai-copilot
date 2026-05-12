# ADR 0004: Use Eval-Driven Agent Validation

## Status

Accepted

## Context

Agent behavior can regress even when code compiles. Route selection, tool choice, grounding, memory behavior, and fallback behavior need explicit checks.

## Decision

Keep JSONL eval datasets and run dry-run validation in CI. Real evals run manually because they require Docker, Odoo, Knowledge DB, and LLM provider calls.

## Consequences

- Behavior is measurable and versionable.
- Real evals remain slower and environment-dependent.
- Latency is reported by default and can be enforced with `EVAL_ENFORCE_LATENCY=true`.
