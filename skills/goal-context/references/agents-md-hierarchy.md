# AGENTS.md Hierarchy And Task Workspace

`goal-context` owns AGENTS.md discovery, missing project AGENTS.md
generation, managed Path Index updates, and `doc/` task workspace checks before
standard or full goal execution. `goal-entry` decides when this preflight is
required, then calls this standalone skill.

## Required Order

Read instruction files in this order:

1. Global AGENTS.md: the path supplied by `--global-agents`, defaulting to
   `$HOME/.codex/AGENTS.md` (or `CODEX_GLOBAL_AGENTS`).
2. Project-root AGENTS.md: `<repo>/AGENTS.md`.
3. Nested AGENTS.md files from project root toward the target path.
4. Current user message and active developer/system constraints.

When instructions conflict, later and closer scope wins, except the current
user message and higher-priority platform instructions always override
AGENTS.md files.

## Project Generation

For standard/full execution, run:

```bash
python3 <codex-skills-root>/goal-context/scripts/ensure_agents_context.py \
  --repo-root <repo> \
  --target-path <path> \
  --create-missing-project-agents \
  --require-project-agents \
  --init-doc-workspace \
  --record-boot \
  --include-path-index \
  --update-project-path-index \
  --task-id <goal-or-run-id> \
  --task-summary "<short task summary>" \
  --json
```

If the project-root AGENTS.md exists, read it and do not overwrite it. If it
does not exist, generate the minimal project template and then read it. Nested
AGENTS.md files are never generated automatically; they are read when present.

Use `--create-missing-global-agents` only when intentionally bootstrapping the
global file. Do not overwrite an existing global AGENTS.md.

## Path Index

Project-root AGENTS.md should include a managed `Path Index` block. It is
bounded by:

```text
<!-- goal-context:path-index:start -->
...
<!-- goal-context:path-index:end -->
```

Only this block may be updated automatically. Existing human AGENTS.md content
outside the managed block must remain untouched. The legacy
`harness-agents-md-context:path-index` and
`harness-agent-for-goal:path-index` blocks may be replaced in place when the
standalone skill refreshes a previously generated project file.

The path index should include, when present:

- start-here paths requested by the current target plus obvious entry points
  such as `AGENTS.md`, `README.md`, manifests, and Makefiles;
- AGENTS files, including nested `AGENTS.md`;
- workspace units inferred from manifests;
- command/dependency manifests such as `pyproject.toml`, `package.json`,
  `requirements.txt`, and `Makefile`;
- source roots, tests, docs, task docs, generated agent-context metadata, and
  sensitive paths that should not be packed or edited casually.

The machine-readable `agents_context.json` should also include `path_index`
with the same sections. Use `--path-index-max-depth` and
`--path-index-max-items` to keep large repositories bounded.

## Doc Workspace

Task process docs belong under `doc/`:

- `doc/task_plan.md`
- `doc/progress.md`
- `doc/findings.md`
- `doc/task_issue.md`
- `doc/lessons.md`

Before code edits, the orchestrator must read `doc/lessons.md`, record the
current task as in-progress in `doc/task_issue.md`, and initialize or update
`doc/task_plan.md`. During execution, append live progress and findings to
`doc/progress.md` and `doc/findings.md` when the run produces durable evidence,
decisions, blockers, or risks.

If root-level `task_plan.md`, `progress.md`, `findings.md`, `task_issue.md`, or
`lessons.md` exist, stop and move or resolve them before continuing. Do not
carry a separate root process-doc workspace.

## Subagent And Worktree Injection

Every subagent prompt or worktree assignment must receive:

- the resolved `agents_chain` for its target path;
- the relevant `path_index` summary for the project when available;
- the nearest AGENTS.md path and scope;
- its write scope and validation contract;
- the doc workspace path when the task needs to update process docs.

Subagents must read and obey the chain from global to nearest, with nearest
scope taking precedence. They must not create branches, create worktrees, merge
work, call Codex goal tools, or edit outside their assigned write scope.

## User-Facing Output

Do not show raw `agents_context.json`, raw subagent notifications, raw JSON, or
tool output unless the user asks for raw artifacts. Final output should state:

- what changed;
- what the result is;
- what decision remains for the user, if any.

Default final answers should stay compact and ordered.
