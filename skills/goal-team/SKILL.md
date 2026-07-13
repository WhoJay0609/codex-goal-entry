---
name: goal-team
description: Select the minimum expert set for explicit Goal work from the goal-backend expert registry. Use before dispatch and independent acceptance.
---

# Goal Team

1. Read `references/team-map.md` and the backend expert registry.
2. Run `scripts/select_goal_experts.py` to select one primary expert for the work unit.
3. Add a specialist only for a real cross-domain boundary or an independent
   acceptance requirement.
4. Record selection through backend capability `evidence.record`.

This skill selects experts but does not dispatch them or change permissions.
Never give an expert Goal tools, `goal-*`, `goal-backend`, or reserved
orchestration skills.
