---
name: goal-preflight
description: Internal readiness gate that validates and binds a model-selected Goal route before Goal mutation, backend initialization, or dispatch.
---

# Goal Preflight

1. Read `references/preflight-contract.md` when changing readiness semantics.
2. Run `scripts/run_goal_preflight.py --model-route-json ...` with the exact
   model route, repository, paths, and readiness evidence used by `goal-entry`.
   Use `--legacy-resolver` only for explicit diagnostics.
3. Stop on `ready=false`; copy a passed result into the Goal Session envelope.
4. Keep this skill main-orchestrator-only. Do not dispatch it to experts.

Validate and bind the model decision; never reclassify it. Do not duplicate
planning, team, dispatch, backend, or closeout policy here.
