# Backend Map

| Capability | Allowed owners | Script |
|---|---|---|
| `run.initialize` | `goal-context`, `goal-dispatch` | `scripts/init_goal_run.py` |
| `evidence.record` | `goal-context`, `goal-dispatch`, `goal-team` | `scripts/record_goal_evidence.py`; `scripts/record_runtime_handle.py` |
| `trace.validate` | `goal-trace`, `goal-close` | `scripts/validate_goal_trace.py` |
| `runtime.cleanup` | `goal-close` | `scripts/reclaim_runtime_handles.py` |
| `goal.sync` | `goal-close` | `scripts/finalize_goal_sync.py` |
| `trace.read_legacy` | `goal-trace` | `scripts/read_legacy_trace.py` |

The authorization request carries main-orchestrator actor, owner, capability,
Goal id, `goal-entry` decision/session, and passed preflight. Fingerprints and
Goal/session bindings must agree before mutation.

Expert skill authorization is a permission check carried by `evidence.record`.
The CLI requires the same authorized request and run binding, and records both
allow and deny outcomes as `expert_skill_authorization` evidence.
