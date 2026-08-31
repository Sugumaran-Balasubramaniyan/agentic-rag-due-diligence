# ADR 0002: Deterministic provider boundary

## Status

Accepted for Task 1.

## Decision

Task 1 includes no live-provider integration and commits no credentials.
Environment configuration is represented only by `.env.example`; later
provider adapters must remain optional and testable through deterministic
local implementations.

## Consequences

Smoke tests and CI are reproducible offline from application services. Any
future external integration must be introduced in a later task with an
explicit contract and fail-closed tests.
