# Goal Run Artifact Contract

New runs retain additive `manifest.json` schema `goal-run/v1` and append-only
`events.jsonl`. The atomic manifest is authoritative state; events are the audit
and recovery journal. Trace validation rejects binding, lifecycle-revision, and
external-operation divergence.

The manifest carries the immutable Goal/session/scope binding, lifecycle state
and revision, task graph, Issue/PR projections, external operation records, and
bounded recovery counts. External writes use a stable operation id,
desired-state digest, intent, provider reconciliation, and outcome. `pending`
never means a create may be retried blindly.

Lifecycle transitions and recovery actions retain replay identity in the
manifest. If a manifest write succeeds but its audit append is interrupted, a
retry with the same revision or recovery `operation_id` restores the missing
event without repeating the state change. Issue and PR replays likewise restore
missing intent/outcome events before returning reconciliation instructions.

Provider credentials and arbitrary provider payloads are forbidden. Durable
outcomes contain only schema-validated operation/digest/provider identity, URL,
and state. Evidence status remains `completed`, `missing`, `partial`, `failed`,
`blocked`, or `readiness_only`.

Before `active -> verifying`, every accepted milestone has a latest completed
`milestone_acceptance` event with `mechanical_passed: true` and non-empty
`evidence_refs`. Every high-risk work unit has a completed governed `claim`
bound by `work_unit_id` and an eligible independent acceptance. If the run owns
runtime handles, its latest cleanup record must already be completed.

Legacy traces are read without mutation or replay through
`trace.read_legacy`.
