---
name: goal-plan
description: Plan an explicit durable Goal and define integration-ready work units. Use after Goal routing/preflight or for a plan-only Goal handoff; never execute backend capabilities itself.
---

# Goal Plan

Read `references/plan-builder.md`. Define bounded work units with owners,
dependencies, outputs, acceptance evidence, integration checkpoints, and stop
conditions. Keep provider choice, expert selection, and execution outside the
backend.

Planning-only requests stop before Goal mutation, edits, backend initialization,
or dispatch. This skill is main-orchestrator-only.
