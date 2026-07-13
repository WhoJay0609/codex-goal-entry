# AGENTS.md

## Repository Purpose

This repository publishes the public `goal-entry` router and its private
`goal-*` family skills. Keep the public router small and the family protocols
explicit, readable, and safe to reuse outside the author's local machine.

## Editing Rules

- Preserve exact identifiers such as `goal-entry`, `Goal`, `subagent`,
  `SKILL.md`, `resolve_goal_entry.py`, and `create_goal`.
- Do not add local absolute paths, private machine assumptions, or secret
  material.
- Keep `goal-entry` router-only. Detailed execution protocol belongs in
  the internal `goal-*` child skills under `skills/`.
- Keep examples bilingual-friendly, but prefer Chinese explanations for this
  public package.

## Validation

Run before claiming completion:

```bash
python3 scripts/quick_validate.py .
python3 scripts/resolve_goal_entry.py --request 'PLEASE IMPLEMENT THIS PLAN with tests' --readiness-status passed
python3 scripts/check_goal_stack.py .
python3 -m unittest discover -s tests -p 'test_*.py'
```
