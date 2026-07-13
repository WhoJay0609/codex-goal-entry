# Backend Map

| Capability | Allowed owners | Script |
|---|---|---|
| `run.initialize` | `goal-context`, `goal-dispatch` | `scripts/init_goal_run.py` |
| `evidence.record` | `goal-context`, `goal-dispatch`, `goal-team` | `scripts/record_goal_evidence.py`; `scripts/record_runtime_handle.py`; `scripts/advance_goal_lifecycle.py`; `scripts/sync_issue_projection.py`; `scripts/record_recovery_action.py` |
| `trace.validate` | `goal-trace`, `goal-close` | `scripts/validate_goal_trace.py`; `scripts/advance_goal_lifecycle.py` |
| `runtime.cleanup` | `goal-close` | `scripts/reclaim_runtime_handles.py` |
| `goal.sync` | `goal-close` | `scripts/finalize_goal_sync.py`; `scripts/advance_goal_lifecycle.py` |
| `trace.read_legacy` | `goal-trace` | `scripts/read_legacy_trace.py` |

The authorization request carries main-orchestrator actor, owner, capability,
Goal id, `goal-entry` decision/session, and passed preflight. Fingerprints and
Goal/session bindings must agree before mutation.

Authorization also carries `operation_phase`. Initialization and planning
evidence require `planning_mutation_allowed`; active, verifying, cleanup, and
closeout work require `phase_execution_allowed`. The backend never reclassifies
the model route.

Expert skill authorization is a permission check carried by `evidence.record`.
The CLI requires the same authorized request and run binding, and records both
allow and deny outcomes as `expert_skill_authorization` evidence.
