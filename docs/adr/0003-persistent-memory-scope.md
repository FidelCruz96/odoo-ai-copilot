# ADR 0003: Scope Persistent Memory by Database, User, and Session

## Status

Accepted

## Context

Follow-up questions need memory, but ERP systems are multi-user and often multi-company or multi-database. A weak memory key can leak context between users.

## Decision

Persist conversation memory using `db_name + user_id + session_id`. Request-provided memory takes precedence over persisted memory, and explicit entities take precedence over both.

## Consequences

- Follow-ups work without relying only on frontend history.
- Cross-user and cross-database leakage risk is reduced.
- Production deployments should use PostgreSQL or Redis-backed storage, not process-local memory.
