# Closeout Contract

Completion requires no owned runtime handles, valid trace evidence, all governed
claims independently accepted, all work units integrated, and pre/post Goal sync
records. Completion also requires original `pr.create` authorization and a
schema-validated PR identity reconciled against its operation intent. An
authorized PR must reconcile to an open provider state. An unauthorized PR
remains a draft and an ambiguous result remains `verifying`.
Merge and post-PR review do not reopen completed state. Blocked status follows
the Goal tool's repeated-blocker contract and requires ordered pre/post blocked
sync records before the lifecycle becomes terminal.

Only the main orchestrator calls Goal tools; backend sync records the call but
does not perform it.
