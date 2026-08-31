# ADR 0003: Deterministic CI host boundary

## Status

Accepted for Task 1 Fix Round 2.

## Decision

CI uses the explicit `ubuntu-24.04` GitHub-hosted runner label. Every GitHub
Action is pinned to a full commit SHA, and Python and Node use exact patch
versions compatible with the lockfiles.

Actions and language runtimes remain full-version/SHA pinned while GitHub
controls patching of the hosted `ubuntu-24.04` image.

## Consequences

Workflow dependencies and language versions cannot silently move between CI
runs. The hosted image remains an external platform boundary and is therefore
documented rather than falsely treated as fully immutable.
