---
name: goal-entry
description: Router-only public entry for Codex goal work. Use when a request must be classified before goal creation, active-goal binding, planning, dispatch, AGENTS.md context setup, backend run initialization, or closeout.
---

# Goal Entry

Invocation:
`[$goal-entry](SKILL.md)`

Use this as the primary public entry for goal-bound work. It is intentionally
thin: resolve the request, then read the child skill that owns the needed
protocol. Do not duplicate mode, tier, dispatch, objective, or closeout policy
in this file.

Legacy entry points remain installed for compatibility:

- `harness-agent-for-goal`
- `harness-agent`
- `harness-agents-md-context`

In a standalone installation, these legacy entries and the child `goal-*`
skills are optional dependencies. The resolver in this repository can still be
used by itself to classify requests and decide whether goal creation, active
goal binding, planning, dispatch, or closeout should happen.

## Route

1. Run or equivalently apply `scripts/resolve_goal_entry.py` before creating a
   goal, binding an active goal, initializing run artifacts, or dispatching
   subagents for non-trivial work.
2. Treat the resolver output as the only source of truth for `request_mode`,
   `goal_entry_tier`, `superpowers_dispatch_level`, `subagent_execution_mode`,
   route intent, readiness state, and goal action.
3. For `execute_goal` or `active_goal_bind`, read
   `goal-preflight`
   and run `goal-preflight/scripts/run_goal_preflight.py` before goal
   creation, active-goal binding, backend artifact initialization, edits, or
   dispatch. Stop when `ready=false`.
4. For planning and boundary questions, read
   `goal-plan`.
5. Before `create_goal`, read
   `goal-objective`.
6. Before repo-bound standard or full execution, read
   `goal-context`.
7. Before subagent/team dispatch, read
   `goal-dispatch` and, when expert selection is needed, `goal-team`.
8. For artifact-producing runs, read
   `goal-backend`.
9. Before final completion claims, read
   `goal-trace` and `goal-close`.
10. When maintaining the skill stack or generated metadata, read
   `goal-metadata`.

## Hard Rules

- Do not create nested Codex goals.
- Do not call `create_goal` before readiness is explicit.
- Do not call `create_goal` with an objective longer than 4,000 characters.
- Do not let subagents call `get_goal`, `create_goal`, or `update_goal`.
- Do not assign `goal-*` or legacy harness protocol skills to runtime or
  Superpowers subagent `allowed_skills`.
- Do not bypass `resolve_goal_entry.py` with hand-written mode logic.
- Do not bypass `goal-preflight` for `execute_goal` or `active_goal_bind`.

## Validation

```bash
python3 scripts/quick_validate.py .
python3 scripts/resolve_goal_entry.py --request 'PLEASE IMPLEMENT THIS PLAN' --readiness-status passed
```
