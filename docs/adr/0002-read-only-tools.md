# ADR 0002: Keep Odoo Tools Read-Only

## Status

Accepted

## Context

ERP writes require stronger approval workflows, rollback controls, and human confirmation. The current assistant is intended for analysis, lookup, and compliance evidence.

## Decision

Expose only read-only operations through the Odoo bridge: search, read, grouped reads, and counts. Mutating ORM methods are not available to the AI Service.

## Consequences

- Lower blast radius if the model or prompt is wrong.
- Simpler security review.
- Future write actions must use explicit approval flows and separate audit rules.
