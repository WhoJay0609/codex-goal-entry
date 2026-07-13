---
name: goal-backend
description: Private mechanical backend for verified explicit Goal Sessions. Use only from the main orchestrator through an owning goal-* skill for run initialization, evidence, validation, cleanup, Goal sync, legacy reads, and expert permission checks.
---

# Goal Backend

Read `references/backend-map.md`. Authorize every capability before mutation
with `scripts/authorize_backend_call.py`. Supported capabilities are exactly:

- `run.initialize`
- `evidence.record`
- `trace.validate`
- `runtime.cleanup`
- `goal.sync`
- `trace.read_legacy`

Reject direct user, Compound Engineering, unrelated-skill, and subagent calls.
Do not plan, choose providers, select experts, form teams, dispatch, or set retry
policy. Expert skill calls must pass `scripts/authorize_expert_skill.py` and the
global deny; the script requires Goal-authorized `evidence.record` input and
records both allowed and denied decisions. This boundary is protocol
enforcement, not an OS sandbox.
