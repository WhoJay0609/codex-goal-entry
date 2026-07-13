---
name: goal-objective
description: Build the compact objective used to create or bind an explicit durable Goal. Use after goal-entry and goal-preflight authorize Goal lifecycle.
---

# Goal Objective

Read `references/objective-contract.md`, check for an active Goal, and build a
compact objective containing outcome, scope, evidence, constraints, closeout,
and stop conditions. Keep the objective at or below 4,000 characters.

Only the main orchestrator may call Goal tools. Do not create nested Goals and
do not hide missing or failed evidence.
