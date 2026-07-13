---
name: goal-context
description: Resolve AGENTS.md hierarchy, managed path indexes, and task workspace context for explicit Goal work. Use before repository edits or dispatch after Goal preflight passes.
---

# Goal Context

1. Read `references/agents-md-hierarchy.md`.
2. Run `scripts/ensure_agents_context.py` for each target repository/path.
3. Stop when `stop_required=true`.
4. For artifact-producing work, ask the main orchestrator to initialize the run
   through `goal-backend` capability `run.initialize`, then record context with
   `evidence.record`.

Preserve human AGENTS content, update only managed blocks, and keep process
files under `doc/`. This skill is main-orchestrator-only.
