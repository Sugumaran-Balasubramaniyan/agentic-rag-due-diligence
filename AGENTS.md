# Repository instructions

- Treat `docs/superpowers/specs/2026-08-31-due-diligence-copilot-design.md` as the product authority.
- Execute `docs/superpowers/plans/2026-08-31-due-diligence-copilot-implementation.md` task by task.
- Use test-driven development for production behavior: observe the relevant test fail before implementing it.
- Preserve document provenance and workspace isolation through every layer.
- Never commit credentials, private documents, generated model weights, or runtime data.
- Do not claim production use, quality metrics, latency, or deployment status without reproducible evidence.
- Keep the public demo read-only and deterministic by default.
- Update `FUTURE_HANDOFF.md` at every accepted milestone.
- Each independently reviewed task is a checkpoint; after acceptance, the controller pushes that checkpoint only after fresh verification.

