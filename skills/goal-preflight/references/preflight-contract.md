# Goal Preflight Contract

`goal-preflight` is the mechanical gate between a model-selected Goal route and
Goal mutation. It validates the route envelope, binds objective, authorization,
idempotency identity, and verified cursor, then emits one planning Goal Session.
It never chooses or changes the execution level.

Normal callers pass `--model-route-json` containing
`goal-entry.model-route.v1`. The `goal-preflight.preflight.v2` result includes
readiness, the bound decision and stable session identity, planning lifecycle
state, idempotency outcome, verified resume Goal id, and repository context.

Direct, Compound, and none routes return `entry_route_not_goal_lifecycle` and
create no Goal Session. Resume requires a `goal-context` verified cursor.
`--existing-session-json` replays a matching identity and fails closed when its
fingerprint or verified resume cursor changes. For an inherited short reply,
the fingerprint uses the prior task's `authoritative_instruction`; the short
reply remains in the current route for audit without changing task identity.
`--legacy-resolver` is diagnostics/offline compatibility, not the normal path.

Planning sessions grant `planning_mutation_allowed` but not
`phase_execution_allowed`. Backend authorization combines capability and phase,
so planning may proceed without granting expert execution. `goal-context` owns
AGENTS.md and `doc/` resolution; the main orchestrator carries the complete
preflight and decision into backend calls.
