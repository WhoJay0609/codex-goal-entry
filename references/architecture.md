# Goal Skill Architecture

`goal-entry` is the public router. It owns no detailed execution protocol.

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

The resolver's version-1 top-level fields remain the compatibility projection.
The additive `decision_contract` version 2 exposes profile, lifecycle,
authorization, provider gaps, verifier requirements, and the next external
owner. Provider status is orthogonal to lifecycle: a missing provider changes
the handoff posture without inventing a new progress state.

Legacy `harness-*` skills remain installed for old prompts and generated
references. New policy should be added to the appropriate `goal-*` skill first;
legacy wrappers should only point back to the new owner or the compatibility
backend surface.
