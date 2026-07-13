# Goal Preflight Contract

`goal-preflight` is the lightweight execution gate between `goal-entry` routing
and goal-bound execution. It answers one question: can this request safely enter
the execution protocol now?

## JSON Contract

`scripts/run_goal_preflight.py` emits this narrow JSON object:

- `schema`: `goal-preflight.preflight.v1`
- `ready`: boolean, false when any hard blocker exists.
- `blockers`: hard-stop strings.
- `warnings`: non-blocking strings.
- `request_mode`: copied from the `goal-entry` resolver.
- `goal_action`: copied from the `goal-entry` resolver.
- `execution_destination`: must be `goal_lifecycle` before Goal execution.
- `entry_session_id` and `request_fingerprint`: copied from the Goal Entry
  Session for backend binding.
- `objective_length`: integer or null.
- `goal_action_allowed`: boolean.
- `repo_bound`: boolean.
- `artifact_run_required`: boolean.
- `context_required`: boolean.
- `agents_context`: embedded `goal-context` JSON or null.

## Hard Blockers

Fail closed only for:

- objective length greater than 4,000 characters;
- missing `repo_root`;
- missing target path;
- `goal-context.stop_required=true`;
- execution request that would need `create_goal` while readiness is not
  `passed`.

Warnings are informative and must not change `ready`.

## Ownership

`goal-entry` owns routing. `goal-context` owns AGENTS.md and `doc/` workspace
resolution. `goal-preflight` owns only the gate that composes those results.
The main orchestrator passes the emitted JSON in the backend authorization
envelope. The backend validates its session and request bindings before mutation.
