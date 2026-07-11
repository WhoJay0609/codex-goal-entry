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
   route intent, readiness state, goal action, typed `decision_contract`, and
   authoritative additive `entry_session`.
   The typed contract selects a Runtime Profile and reports lifecycle,
   authorization, provider compatibility, verifier separation, and next owner.
   The Entry Session runs a deterministic Semantic Pass followed by an
   Authority Pass that may narrow, but never broaden or reinterpret, mutation
   authority.
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

## Runtime Profiles

- `complex_engineering` covers context, boundaries, implementation,
  integration, validation, delivery, and closeout.
- `scientific_autoresearch` covers research bootstrap, protocol lock,
  experiment and synthesis loops, evidence review, Claim Firewall, and writing
  handoff.
- Both profiles use the Shared Goal Kernel contract in
  `references/runtime_profiles.json`. This public router reports the contract;
  external child owners perform roadmap, milestone, verification, reclamation,
  and closeout actions.
- Pass durable state with `--runtime-state-json` for resume decisions and a
  capability manifest with `--capabilities-json` to distinguish full-stack,
  degraded, standalone, and incompatible provider surfaces.
- Treat caller durable state and capability declarations as discovery and
  compatibility inputs only. Binding/resume requires a verified
  `goal-context` cursor; phase execution requires a healthy, unexpired,
  session-scoped attestation from the trusted `goal-preflight` adapter.
- Composite requests compile explicit ordered clauses into one Goal phase
  graph. Profiles are phase-scoped; `goal-plan` still owns milestones and the
  approved roadmap.

## Hard Rules

- Do not create nested Codex goals.
- Do not call `create_goal` before readiness is explicit.
- Do not call `create_goal` with an objective longer than 4,000 characters.
- Do not let subagents call `get_goal`, `create_goal`, or `update_goal`.
- Do not assign `goal-*` or legacy harness protocol skills to runtime or
  Superpowers subagent `allowed_skills`.
- Do not bypass `resolve_goal_entry.py` with hand-written mode logic.
- Do not bypass `goal-preflight` for `execute_goal` or `active_goal_bind`.
- Do not mutate when the Semantic Pass is ambiguous, idempotency conflicts,
  cursor revision is stale, Goal selection is unresolved, or the Authority
  Pass denies Goal mutation.
- Do not schedule a phase unless `phase_execution_allowed=true`; legacy
  `provider_status=full_stack` is declaration coverage only.
- Do not treat a declared capability or a passing conformance trace as proof
  that an external provider performed real Goal mutations.
- Do not accept a milestone without an independent verifier and cleanup
  evidence, or promote a scientific claim through a blocked Claim Firewall.

## Validation

```bash
python3 scripts/quick_validate.py .
python3 scripts/resolve_goal_entry.py --request 'PLEASE IMPLEMENT THIS PLAN' --readiness-status passed
python3 scripts/validate_goal_runtime.py tests/fixtures/engineering_runtime_trace.json tests/fixtures/autoresearch_runtime_trace.json
```
