# Goal Skill Architecture

`goal-entry` is the public router. It owns no detailed execution protocol.

Primary responsibility split:

- `goal-entry`: resolve request mode, tier, dispatch level, execution mode, and
  goal action.
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

Legacy `harness-*` skills remain installed for old prompts and generated
references. New policy should be added to the appropriate `goal-*` skill first;
legacy wrappers should only point back to the new owner or the compatibility
backend surface.
