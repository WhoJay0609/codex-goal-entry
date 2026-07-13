---
name: goal-entry
description: Minimal explicitly invoked router for direct read-only work, Compound Engineering, or a durable Goal lifecycle.
---

# Goal Entry

Invocation: `[$goal-entry](SKILL.md)`

Use this skill only when the user explicitly invokes `goal-entry`. It is a thin
entry decision, not a wrapper around every task and not another project manager.

## Choose one execution level

Use the full conversation and your own judgment to produce one compact
`goal-entry.model-route.v1` record. Read
`references/model_route_contract.json` first and populate its required fields;
Goal routes also carry a stable `idempotency_key`:

- `direct`: read-only answering, inspection, explanation, or diagnosis. It may
  not change artifacts.
- `compound`: one bounded artifact-changing engineering task. Prefer a
  user-named professional skill and let Compound Engineering own the work unit.
- `goal`: work needs durable lifecycle state, cross-turn resume, dependent
  stages, milestones, repeated iteration, monitoring, or multi-stage acceptance.
- `none`: the user said not to execute or the request is not ready for mutation.

Goal selection does not require the literal word “Goal” after this skill was
invoked. Upgrade project-shaped work when one bounded Compound run is not a
reliable completion boundary. Inside a Goal, Compound Engineering still executes
bounded engineering units; Goal owns only lifecycle, dependencies, evidence,
recovery, acceptance, and closeout.

Keep a named professional skill as `preferred_skill`. A short reply such as
`1`, `继续`, or `可以` inherits the active task, execution level, preferred
skill, and authorization; copy the prior route fields into `inherited_context`
so the validator can reject task or scope drift. Without that active context it
is not independently routable.

Explicit no-execution wording is a hard veto. When meaning is uncertain, begin
with read-only inspection and ask only if the remaining choice changes scope,
authorization, irreversible risk, or the evidence needed for completion.

## Run the selected level

- `direct`: work natively and create no Goal artifacts.
- `compound`: invoke the preferred bounded Compound/professional skill and
  create no Goal artifacts.
- `goal`: validate the model route, then run `goal-preflight`. When it passes,
  create or resume one planning Goal and inform the user; do not ask for a
  second confirmation merely to start the authorized lifecycle.
- `none`: do not mutate.

A Goal progresses `planning -> active -> verifying -> completed`, or becomes
`blocked` when its bounded recovery/escalation contract is exhausted. Planning
creates the task graph, milestones, acceptance criteria, and stable Issue
identities. The main orchestrator owns Goal tools and provider calls. Experts may
use only their registered professional skill families and may never call Goal
tools, `goal-*`, backend capabilities, or recursive project orchestrators.

Issue and PR writes are automatic only when the original request authorized
those external actions; otherwise keep drafts. Resume reconciles stable
operation identities before retrying. A Goal completes only after mechanical
checks, required independent acceptance, runtime cleanup, Goal synchronization,
and an authorized reconciled PR identity. Merge and post-PR follow-up are
separate unless the original request includes them.

## Mechanical boundary

- `references/model_route_contract.json` defines the route envelope; it does
  not classify natural language.
- `goal-preflight` validates and binds the model decision but never reclassifies
  it.
- The legacy diagnostic router remains an offline compatibility surface, not
  normal semantic authority.
- Goal objectives remain at most 4,000 characters; resume requires a verified
  `goal-context` cursor.

## Validation

```bash
python3 scripts/quick_validate.py .
python3 scripts/check_goal_stack.py .
python3 -m unittest discover -s tests -p 'test_*.py'
```
