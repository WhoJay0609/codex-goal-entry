---
name: goal-trace
description: Validate new Goal evidence or read historical traces without replay. Use before Goal closeout or any completion, dispatch, cleanup, or acceptance claim.
---

# Goal Trace

Read `references/trace-map.md`. Ask the main orchestrator to call backend
`trace.validate` for new runs or `trace.read_legacy` for historical runs.

Report completed, missing, partial, failed, blocked, and readiness-only evidence
distinctly. Never replace validator results with prose, mutate a legacy trace,
or reactivate its old mode/provider policy. This skill is main-orchestrator-only.
