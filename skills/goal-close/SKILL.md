---
name: goal-close
description: Close an explicit Goal after cleanup, trace validation, independent acceptance, and Goal synchronization. Use before any complete or blocked status update.
---

# Goal Close

Read `references/closeout-contract.md` and execute in order:

1. Reconcile runtime handles through backend `runtime.cleanup`.
2. Validate trace and required independent acceptance through `goal-trace`.
3. Record the authorized PR intent, reconcile its provider identity, and keep
   unauthorized PR work as a draft.
4. Record pre-update synchronization through backend `goal.sync`.
5. Let only the main orchestrator call the Goal status tool.
6. Record post-update synchronization through backend `goal.sync`, then commit
   the internal `verifying -> completed` transition.

Never mark completion because time/budget expired or hide failed evidence.
