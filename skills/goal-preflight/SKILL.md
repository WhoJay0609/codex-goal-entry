---
name: goal-preflight
description: Internal readiness gate for explicit durable Goal creation or resume. Use only after goal-entry selects Goal lifecycle and before Goal mutation, backend initialization, or dispatch.
---

# Goal Preflight

1. Read `references/preflight-contract.md` when changing readiness semantics.
2. Run `scripts/run_goal_preflight.py` with the same request, objective, Goal
   snapshot, repository, paths, and readiness evidence used by `goal-entry`.
3. Stop on `ready=false`; copy a passed result into the Goal Session envelope.
4. Keep this skill main-orchestrator-only. Do not dispatch it to experts.

Do not duplicate planning, team, dispatch, backend, or closeout policy here.
