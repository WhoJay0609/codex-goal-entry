# Goal Entry Architecture

`goal-entry` is an explicitly invoked semantic entry. The model chooses one
execution level from the full conversation; deterministic code validates the
decision envelope and Goal mechanics without reproducing that judgment.

## Ownership

| Surface | Owner |
| --- | --- |
| Semantic level and preferred skill | Main model orchestrator |
| Read-only answer or inspection | Native/direct execution |
| Bounded artifact mutation | Compound Engineering or named professional skill |
| Goal readiness and trusted session binding | `goal-preflight` |
| Objective, context, graph, dispatch, experts | Relevant `goal-*` protocol |
| Lifecycle state, evidence, recovery, projections, cleanup, sync | Six-capability `goal-backend` kernel |
| Issue/PR provider calls and Goal tools | Main orchestrator only |

The model route has four values: `direct`, `compound`, `goal`, and `none`.
`references/model_route_contract.json` validates shape, direct-write exclusion,
no-execution precedence, short-reply inheritance, objective length, external
authorization, and trusted resume cursor. It contains no phrase classifier or
skill-selection registry.

## Goal lifecycle

New Goal sessions start in `planning`, then move monotonically through `active`
and `verifying` to `completed`; `blocked` is terminal. An atomic manifest is the
authoritative state. Append-only events are the audit and recovery journal, not
a second planner or a general event-sourcing platform.

Planning records a stable graph, milestones, acceptance criteria, work units,
and Issue mapping keys. External operations use a write-ahead intent, stable
operation identity, desired-state digest, provider reconciliation, and a bound
outcome. An ambiguous provider call is reconciled before retry; it is never
blindly recreated.

The backend retains exactly six public capabilities. Planning initialization,
evidence/projection recording, trace validation, runtime cleanup, Goal sync, and
legacy trace reading stay behind their current owner allowlist. Capability and
lifecycle phase are both checked, so planning authority cannot execute a work
unit.

## Completion

Every milestone needs mechanical evidence. High-risk work and the final PR claim
need an independent eligible verifier. Completion additionally requires accepted
work, reconciled runtime handles, ordered Goal synchronization, original PR
authorization, and a schema-validated reconciled PR identity. Provider
credentials and raw provider payloads never enter durable Goal artifacts.

The legacy resolver and runtime traces remain readable for diagnostics and
regression tests, but normal public routing and model-route preflight do not call
that resolver.
