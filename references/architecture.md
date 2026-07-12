# Goal Entry Architecture

`goal-entry` is a narrow boundary between ordinary Compound Engineering work
and an explicit durable Goal lifecycle.

## Ownership

| Surface | Owner |
| --- | --- |
| Normal implementation, debugging, tests, review, bounded plans | Compound Engineering |
| Detecting an explicit durable Goal or explicit Goal resume | `goal-entry` |
| Readiness before Goal creation or binding | `goal-preflight` |
| Goal objective and verified resume cursor | `goal-objective`, `goal-context` |
| Goal roadmap, dispatch, backend artifacts, trace, closeout | External `goal-*` child skills |

The resolver first selects `execution_destination`:

- `compound_engineering`: return the minimal routing envelope. Do not parse or
  emit Goal lifecycle state.
- `goal_lifecycle`: emit the Goal-only `decision_contract` and `entry_session`.
- `null`: no execution route.

This order is deliberate: an active Goal record never turns an ordinary task
into a Goal task. The user must explicitly request a durable Goal outcome or a
Goal resume.

## Goal lifecycle contract

Only the Goal route evaluates runtime profiles, durable state, capability
declarations, idempotency, cursor selection, and provider attestations.
`entry_session_contract.json` defines the two ordered passes:

1. Semantic Pass identifies the authoritative instruction, ambiguity, and any
   phase graph.
2. Authority Pass can only narrow that result using verified cursor and
   provider evidence.

The resolver validates the shape of external evidence; it does not claim the
external provider performed a real mutation. Goal tools remain main-agent only;
subagents cannot create, update, or close Goals.

`runtime_profiles.json` remains policy data for explicit Goal workflows. Its
trace validator is read-only and never schedules work or mutates state.
