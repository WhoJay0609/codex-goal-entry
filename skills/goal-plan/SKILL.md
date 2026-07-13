---
name: goal-plan
description: Plan an explicit durable Goal and define integration-ready work units. Use after Goal routing/preflight or for a plan-only Goal handoff; never execute backend capabilities itself.
---

# Goal Plan

Read `references/plan-builder.md`. Define the durable task graph with stable
milestone/work-unit ids, dependencies, outputs, acceptance criteria, risk,
integration checkpoints, and stop conditions. Each milestone gets one primary
Issue projection; create a child Issue only for an independently deliverable,
independently accepted, or blocking unit. Keep provider choice, expert
selection, and execution outside the backend.

The main orchestrator passes the graph to `goal-dispatch`, which records it
through backend `evidence.record`; `goal-plan` does not mutate backend state
directly. This skill is main-orchestrator-only.
