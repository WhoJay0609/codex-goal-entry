from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import authorization, load_script


GRAPH = {
    "version": 1,
    "milestones": [
        {
            "id": "m1",
            "title": "Ship",
            "acceptance_criteria": ["tests pass"],
            "status": "planned",
        }
    ],
    "work_units": [
        {
            "id": "u1",
            "milestone_id": "m1",
            "dependencies": [],
            "status": "planned",
            "risk": "high",
        }
    ],
}


class PrCompletionGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.init = load_script("init_goal_run.py")
        self.lifecycle = load_script("advance_goal_lifecycle.py")
        self.issue = load_script("sync_issue_projection.py")
        self.record = load_script("record_goal_evidence.py")
        self.cleanup = load_script("reclaim_runtime_handles.py")
        self.sync = load_script("finalize_goal_sync.py")

    def _reach_verifying(self, run_dir: Path) -> dict:
        actions = ["issue.create", "pr.create"]
        init_auth = authorization(external_actions=actions)
        self.assertTrue(self.init.initialize_run(init_auth, run_dir)["ok"])
        plan_auth = authorization(
            "goal-dispatch", "evidence.record", external_actions=actions
        )
        plan_auth["operation_phase"] = "planning"
        self.assertTrue(self.lifecycle.store_task_graph(plan_auth, run_dir, GRAPH)["ok"])
        manifest = self.lifecycle.load_manifest(run_dir)
        issue_operation = {
            "operation_id": "issue-m1-v1",
            "mapping_key": "milestone:m1",
            "milestone_id": "m1",
            "issue_kind": "primary",
            "action": "create",
            "scope_digest": manifest["authorization_scope_digest"],
            "desired_state": {"title": "M1", "body": "tests pass"},
        }
        intent = self.issue.sync_issue_projection(plan_auth, run_dir, issue_operation)
        issue_operation["provider_result"] = {
            "operation_id": "issue-m1-v1",
            "desired_state_digest": intent["operation"]["desired_state_digest"],
            "provider_id": "issue-1",
            "url": "https://example.test/issues/1",
            "state": "open",
        }
        self.assertTrue(
            self.issue.sync_issue_projection(plan_auth, run_dir, issue_operation)["ok"]
        )
        self.assertTrue(
            self.lifecycle.advance_lifecycle(
                plan_auth, run_dir, target_state="active", expected_revision=0
            )["ok"]
        )
        active_auth = authorization(
            "goal-dispatch", "evidence.record", external_actions=actions
        )
        self.assertTrue(
            self.lifecycle.update_work_status(
                active_auth,
                run_dir,
                work_units={"u1": "accepted"},
                milestones={"m1": "accepted"},
            )["ok"]
        )
        evidence_auth = authorization(
            "goal-team", "evidence.record", external_actions=actions
        )
        self.assertTrue(
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="milestone_acceptance",
                status="completed",
                data={
                    "milestone_id": "m1",
                    "mechanical_passed": True,
                    "evidence_refs": ["test://focused-suite"],
                },
            )["ok"]
        )
        self.assertTrue(
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="claim",
                status="completed",
                data={
                    "claim_id": "unit-u1",
                    "work_unit_id": "u1",
                    "claim_type": "code",
                    "executor_id": "implementer-1",
                },
            )["ok"]
        )
        self.assertTrue(
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="independent_acceptance",
                status="completed",
                data={
                    "claim_id": "unit-u1",
                    "claim_type": "code",
                    "executor_id": "implementer-1",
                    "verifier_id": "verifier-unit-1",
                    "verifier_expert": "test_and_verification",
                    "accepted": True,
                },
            )["ok"]
        )
        trace_auth = authorization(
            "goal-trace", "trace.validate", external_actions=actions
        )
        trace_auth["operation_phase"] = "verifying"
        self.assertTrue(
            self.lifecycle.advance_lifecycle(
                trace_auth, run_dir, target_state="verifying", expected_revision=1
            )["ok"]
        )
        return {"actions": actions, "manifest": self.lifecycle.load_manifest(run_dir)}

    def test_completion_requires_cleanup_independent_acceptance_and_pr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            context = self._reach_verifying(run_dir)
            close_auth = authorization(
                "goal-close", "goal.sync", external_actions=context["actions"]
            )
            close_auth["operation_phase"] = "closeout"
            early = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="completed", expected_revision=2
            )
            self.assertFalse(early["ok"])
            self.assertIn("authorized_pr_evidence_missing", early["errors"])

            cleanup_auth = authorization(
                "goal-close", "runtime.cleanup", external_actions=context["actions"]
            )
            cleanup_auth["operation_phase"] = "closeout"
            self.assertTrue(self.cleanup.reclaim_runtime_handles(cleanup_auth, run_dir)["ok"])

            pr_operation = {
                "operation_id": "pr-final-v1",
                "scope_digest": context["manifest"]["authorization_scope_digest"],
                "desired_state": {"title": "Ship lifecycle", "body": "Verified"},
            }
            intent = self.sync.record_pr_projection(close_auth, run_dir, pr_operation)
            self.assertEqual("create", intent["provider_action"])
            replay = self.sync.record_pr_projection(close_auth, run_dir, pr_operation)
            self.assertEqual("reconcile", replay["provider_action"])
            pr_operation["provider_result"] = {
                "operation_id": "pr-final-v1",
                "desired_state_digest": intent["operation"]["desired_state_digest"],
                "provider_id": "pr-7",
                "url": "https://example.test/pull/7",
                "state": "open",
            }
            self.assertTrue(
                self.sync.record_pr_projection(close_auth, run_dir, pr_operation)["ok"]
            )
            duplicate = self.sync.record_pr_projection(
                close_auth,
                run_dir,
                {
                    "operation_id": "pr-final-v2",
                    "scope_digest": context["manifest"]["authorization_scope_digest"],
                    "desired_state": {
                        "title": "Duplicate",
                        "body": "Do not create",
                    },
                },
            )
            self.assertEqual("none", duplicate["provider_action"])
            self.assertEqual("pr-7", duplicate["operation"]["provider_id"])

            evidence_auth = authorization(
                "goal-team", "evidence.record", external_actions=context["actions"]
            )
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="claim",
                status="completed",
                data={
                    "claim_id": "final-pr",
                    "claim_type": "release",
                    "executor_id": "implementer-1",
                    "provider_id": "pr-7",
                    "desired_state_digest": intent["operation"][
                        "desired_state_digest"
                    ],
                },
            )
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="independent_acceptance",
                status="completed",
                data={
                    "claim_id": "final-pr",
                    "claim_type": "release",
                    "executor_id": "implementer-1",
                    "verifier_id": "verifier-1",
                    "verifier_expert": "documentation_and_communication",
                    "accepted": True,
                },
            )
            self.assertTrue(
                self.sync.record_goal_sync(
                    close_auth,
                    run_dir,
                    phase="pre_update",
                    goal_status="complete",
                    update_called=False,
                )["ok"]
            )
            self.assertTrue(
                self.sync.record_goal_sync(
                    close_auth,
                    run_dir,
                    phase="post_update",
                    goal_status="complete",
                    update_called=True,
                )["ok"]
            )
            ineligible = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="completed", expected_revision=2
            )
            self.assertFalse(ineligible["ok"])
            self.assertIn(
                "final_independent_acceptance_invalid:verifier_expert_not_eligible",
                ineligible["errors"],
            )
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="independent_acceptance",
                status="completed",
                data={
                    "claim_id": "final-pr",
                    "claim_type": "release",
                    "executor_id": "implementer-1",
                    "verifier_id": "verifier-2",
                    "verifier_expert": "release_and_reliability",
                    "accepted": True,
                },
            )
            completed = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="completed", expected_revision=2
            )
            self.assertTrue(completed["ok"])
            self.assertEqual("completed", completed["manifest"]["lifecycle_state"])
            replay_complete = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="completed", expected_revision=3
            )
            self.assertFalse(replay_complete["ok"])

    def test_forged_pr_outcome_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            context = self._reach_verifying(run_dir)
            close_auth = authorization(
                "goal-close", "goal.sync", external_actions=context["actions"]
            )
            close_auth["operation_phase"] = "closeout"
            operation = {
                "operation_id": "pr-final-v1",
                "scope_digest": context["manifest"]["authorization_scope_digest"],
                "desired_state": {"title": "Ship", "body": "Verified"},
            }
            intent = self.sync.record_pr_projection(close_auth, run_dir, operation)
            operation["provider_result"] = {
                "operation_id": "different-operation",
                "desired_state_digest": intent["operation"]["desired_state_digest"],
                "provider_id": "pr-7",
            }
            result = self.sync.record_pr_projection(close_auth, run_dir, operation)
            self.assertFalse(result["ok"])
            self.assertIn("provider_result_operation_mismatch", result["errors"])

    def test_unauthorized_pr_draft_cannot_be_promoted_by_provider_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            init_auth = authorization()
            self.assertTrue(self.init.initialize_run(init_auth, run_dir)["ok"])
            close_auth = authorization("goal-close", "goal.sync")
            close_auth["operation_phase"] = "closeout"
            manifest = self.lifecycle.load_manifest(run_dir)
            operation = {
                "operation_id": "pr-unauthorized-v1",
                "scope_digest": manifest["authorization_scope_digest"],
                "desired_state": {"title": "Draft", "body": "No grant"},
            }
            draft = self.sync.record_pr_projection(close_auth, run_dir, operation)
            self.assertEqual("draft", draft["operation"]["status"])
            (run_dir / "events.jsonl").unlink()
            repaired = self.sync.record_pr_projection(close_auth, run_dir, operation)
            self.assertTrue(repaired["ok"])
            self.assertEqual("none", repaired["provider_action"])
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("pr_operation_draft", events)
            operation["provider_result"] = {
                "operation_id": "pr-unauthorized-v1",
                "desired_state_digest": draft["operation"][
                    "desired_state_digest"
                ],
                "provider_id": "pr-forged",
                "state": "open",
            }
            rejected = self.sync.record_pr_projection(
                close_auth, run_dir, operation
            )
            self.assertFalse(rejected["ok"])
            self.assertIn(
                "provider_result_for_unauthorized_draft", rejected["errors"]
            )

    def test_completion_requires_open_pr_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            context = self._reach_verifying(run_dir)
            close_auth = authorization(
                "goal-close", "goal.sync", external_actions=context["actions"]
            )
            close_auth["operation_phase"] = "closeout"
            manifest = self.lifecycle.load_manifest(run_dir)
            manifest["pr_projection"] = {
                "status": "applied",
                "provider_id": "pr-closed",
                "provider_state": "closed",
            }
            self.lifecycle.write_json_atomic(run_dir / "manifest.json", manifest)
            result = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="completed", expected_revision=2
            )
            self.assertFalse(result["ok"])
            self.assertIn("authorized_pr_not_open", result["errors"])


if __name__ == "__main__":
    unittest.main()
