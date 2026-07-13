---
name: goal-entry
description: Minimal router for explicit durable Goal creation or resume. Ordinary engineering execution belongs to Compound Engineering.
---

# Goal Entry

Invocation: `[$goal-entry](SKILL.md)`

Use this skill only when the user explicitly asks to create, resume, or run an
**explicit durable Goal**: a long-running, multi-day, autonomous, research, or
otherwise lifecycle-managed outcome. It is not the default entry for coding.

For ordinary engineering work—implementation, debugging, review, testing,
documentation, or a bounded plan—use the appropriate Compound Engineering
workflow instead.

## Route

1. Run `scripts/resolve_goal_entry.py` before creating or resuming a Goal.
   Its `request_mode` and `execution_destination` are the route decision.
2. If `execution_destination=compound_engineering`, do not initialize Goal
   state or read Goal-only inputs. Continue with Compound Engineering.
3. If `execution_destination=goal_lifecycle`, run `goal-preflight` before
   creating or binding a Goal. Stop when readiness is not passed.
4. For a new Goal, use `goal-objective`; for a resume, use `goal-context` and
   its verified cursor.
5. Only after that gate may the Goal family use `goal-plan`, `goal-dispatch`,
   `goal-backend`, `goal-trace`, and `goal-close` as needed.

## What selects Goal mode

Goal mode requires one of these explicit signals:

- Create/start a Goal **and** state a durable outcome, such as long-running,
  multi-day, continuous, autonomous, research loop, or their Chinese forms.
- Explicitly resume or recover an existing Goal.

中文等价表达：`创建一个长期 Goal` / `启动一个科研循环 Goal`，或
`继续这个 Goal` / `恢复这个 Goal`。普通“修复解析器并测试”仍属于 Compound
Engineering。

Execution verbs, research terms, an active Goal record, quoted text, or
delegation flags alone do not select Goal mode. A request that says not to
execute remains non-mutating.

## Goal-only safeguards

- Do not call Goal tools from subagents.
- Do not create or bind a Goal before `goal-preflight` passes.
- Do not create a Goal with an objective longer than 4,000 characters.
- Do not use a caller-supplied record as resume authority; require the verified
  `goal-context` cursor.
- Do not schedule a phase unless the Entry Session's Authority Pass permits it.

## Result contract

Routine Compound results contain only the small routing envelope and omit
`decision_contract` and `entry_session`. Explicit Goal results include the
Goal lifecycle envelope, including Semantic Pass and Authority Pass evidence.

## Validation

```bash
python3 scripts/quick_validate.py .
python3 scripts/resolve_goal_entry.py --request 'Please implement this plan with tests'
python3 scripts/resolve_goal_entry.py --request 'Please create a long-running Goal to implement this plan with tests' --readiness-status passed
```
