# Goal Skill Architecture

`goal-entry` is the public router. It owns interpretation and authority-gate
contracts, but no durable state, provider runtime, scheduling, or detailed
execution protocol.

Primary responsibility split:

- `goal-entry`: resolve request mode, tier, dispatch level, execution mode,
  Runtime Profile, lifecycle, authorization, provider status, and goal action.
- `goal-preflight`: compose the resolver and context checks into a narrow
  execution gate before goal creation, active-goal binding, artifact
  initialization, edits, or dispatch.
- `goal-plan`: plan-only and copy-only handoff contract.
- `goal-objective`: compact `create_goal(objective=...)` contract.
- `goal-context`: AGENTS.md hierarchy, managed Path Index, and `doc/` workspace.
- `goal-dispatch`: Superpowers-first dispatch contract and fallback recording.
- `goal-team`: expert-team selection and maintenance policy.
- `goal-backend`: compatibility facade for the existing backend scripts under
  `harness-agent`.
- `goal-trace`: artifact and trace validation.
- `goal-close`: cleanup, goal-sync, and final completion contract.
- `goal-metadata`: generated inventory, expert library, and health report
  refresh order.

`references/runtime_profiles.json` is the portable Shared Goal Kernel contract.
It declares milestone gates, independent verification, recovery, reclamation,
state precedence, and Claim Firewall outcomes. It is policy data, not a second
scheduler. `scripts/validate_goal_runtime.py` only replays immutable traces for
conformance and never calls Goal tools, controls processes, or mutates runtime
state.

`references/entry_session_contract.json` defines one risk-adaptive Two-Pass
Entry Session. The Semantic Pass reads only the authoritative instruction lane,
locks ambiguity handling, and compiles explicit ordered clauses into one
phase-aware Goal intent. The Authority Pass consumes that immutable result and
can only narrow it through idempotency, canonical cursor, revision, Goal
selection, and active-phase provider-attestation checks.

Canonical cursors and provider attestations remain externally issued evidence.
The resolver validates typed issuer, scope, status, revision or capability,
health, validity window, and proof-reference fields; it does not perform the
external verification or claim that a real mutation occurred. Missing provider
evidence may leave Goal creation and roadmap planning available while blocking
the affected phase.

The resolver's version-1 top-level fields remain the compatibility projection.
The additive `decision_contract` version 2 exposes profile, lifecycle,
authorization, provider gaps, verifier requirements, and the next external
owner. Provider status is orthogonal to lifecycle: a missing provider changes
the handoff posture without inventing a new progress state.
Legacy `provider_status=full_stack` describes declared capability coverage only.
The authoritative execution signal is
`entry_session.authority_pass.phase_execution_allowed`.

Legacy `harness-*` skills remain installed for old prompts and generated
references. New policy should be added to the appropriate `goal-*` skill first;
legacy wrappers should only point back to the new owner or the compatibility
backend surface.
