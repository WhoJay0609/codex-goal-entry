---
name: goal-dispatch
description: Select and record provider-neutral dispatch for explicit Goal work. Use after goal-plan and goal-team define integration-ready units and experts.
---

# Goal Dispatch

Read `references/dispatch-contract.md`. The main orchestrator selects an
available provider for each unit, enforces repository/write-scope isolation,
and records decisions through `goal-backend` capability `evidence.record`.

Do not default to any provider or historical orchestration mode.
Do not assign Goal tools, `goal-*`, `goal-backend`, or reserved orchestration
skills to experts. This skill owns dispatch decisions, not backend execution.
