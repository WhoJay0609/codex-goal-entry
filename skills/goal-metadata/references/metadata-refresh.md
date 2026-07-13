# Metadata Refresh

Run `scripts/update_skill_inventory.py`, then
`scripts/generate_goal_stack_health.py`, then the repository-level
`scripts/check_goal_stack.py`. The package check treats public `goal-entry` and
the ten internal `goal-*` skills as one atomic installed surface and reports
drift in either part. Generated inventory reports installed and unregistered
skills; only a reviewed edit to the backend family registry grants permission.
