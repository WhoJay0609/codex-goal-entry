from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import authorization, load_script


class IssueProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.init = load_script("init_goal_run.py")
        self.sync = load_script("sync_issue_projection.py")

    def operation(self, run_dir: Path, **updates) -> dict:
        manifest = json.loads((run_dir / "manifest.json").read_text())
        value = {
            "operation_id": "issue-m1-v1",
            "mapping_key": "milestone:m1",
            "milestone_id": "m1",
            "issue_kind": "primary",
            "action": "create",
            "scope_digest": manifest["authorization_scope_digest"],
            "desired_state": {"title": "M1 lifecycle", "body": "Acceptance: tests pass"},
        }
        value.update(updates)
        return value

    def test_write_ahead_intent_reconciles_without_duplicate_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            auth = authorization(
                "goal-dispatch",
                "evidence.record",
                external_actions=["issue.create", "issue.update"],
            )
            auth["operation_phase"] = "planning"
            self.init.initialize_run(authorization(external_actions=["issue.create", "issue.update"]), run_dir)
            first = self.sync.sync_issue_projection(auth, run_dir, self.operation(run_dir))
            self.assertTrue(first["ok"])
            self.assertEqual("create", first["provider_action"])
            replay = self.sync.sync_issue_projection(auth, run_dir, self.operation(run_dir))
            self.assertEqual("reconcile", replay["provider_action"])

            result = {
                "operation_id": "issue-m1-v1",
                "desired_state_digest": first["operation"]["desired_state_digest"],
                "provider_id": "issue-42",
                "url": "https://example.test/issues/42",
                "state": "open",
            }
            applied = self.sync.sync_issue_projection(
                auth, run_dir, self.operation(run_dir, provider_result=result)
            )
            self.assertEqual("applied", applied["operation"]["status"])
            again = self.sync.sync_issue_projection(auth, run_dir, self.operation(run_dir))
            self.assertEqual("none", again["provider_action"])
            self.assertEqual("issue-42", again["operation"]["provider_id"])

    def test_unauthorized_write_is_draft_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            auth = authorization("goal-dispatch", "evidence.record")
            auth["operation_phase"] = "planning"
            self.init.initialize_run(authorization(), run_dir)
            result = self.sync.sync_issue_projection(auth, run_dir, self.operation(run_dir))
            self.assertTrue(result["ok"])
            self.assertEqual("draft", result["operation"]["status"])
            self.assertEqual("none", result["provider_action"])
            replay = self.sync.sync_issue_projection(
                auth, run_dir, self.operation(run_dir)
            )
            self.assertEqual("none", replay["provider_action"])
            forged = self.operation(
                run_dir,
                provider_result={
                    "operation_id": "issue-m1-v1",
                    "desired_state_digest": result["operation"][
                        "desired_state_digest"
                    ],
                    "provider_id": "issue-forged",
                    "state": "open",
                },
            )
            rejected = self.sync.sync_issue_projection(auth, run_dir, forged)
            self.assertFalse(rejected["ok"])
            self.assertIn(
                "provider_result_for_unauthorized_draft", rejected["errors"]
            )

    def test_replan_updates_existing_issue_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            actions = ["issue.create", "issue.update"]
            init_auth = authorization(external_actions=actions)
            auth = authorization(
                "goal-dispatch", "evidence.record", external_actions=actions
            )
            auth["operation_phase"] = "planning"
            self.init.initialize_run(init_auth, run_dir)

            create = self.operation(run_dir)
            intent = self.sync.sync_issue_projection(auth, run_dir, create)
            create["provider_result"] = {
                "operation_id": "issue-m1-v1",
                "desired_state_digest": intent["operation"]["desired_state_digest"],
                "provider_id": "issue-42",
                "url": "https://example.test/issues/42",
                "state": "open",
            }
            self.assertTrue(
                self.sync.sync_issue_projection(auth, run_dir, create)["ok"]
            )

            update = self.operation(
                run_dir,
                operation_id="issue-m1-v2",
                action="update",
                desired_state={
                    "title": "M1 lifecycle",
                    "body": "Acceptance: tests and review pass",
                },
            )
            update_intent = self.sync.sync_issue_projection(auth, run_dir, update)
            self.assertEqual("update", update_intent["provider_action"])
            self.assertEqual(
                "issue-42", update_intent["operation"]["target_provider_id"]
            )
            update["provider_result"] = {
                "operation_id": "issue-m1-v2",
                "desired_state_digest": update_intent["operation"][
                    "desired_state_digest"
                ],
                "provider_id": "issue-42",
                "url": "https://example.test/issues/42",
                "state": "open",
            }
            applied = self.sync.sync_issue_projection(auth, run_dir, update)
            self.assertTrue(applied["ok"])
            self.assertEqual("issue-42", applied["operation"]["provider_id"])
            self.assertEqual(
                "Acceptance: tests and review pass",
                applied["operation"]["desired_state"]["body"],
            )

    def test_update_without_existing_projection_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            actions = ["issue.update"]
            self.init.initialize_run(authorization(external_actions=actions), run_dir)
            auth = authorization(
                "goal-dispatch", "evidence.record", external_actions=actions
            )
            auth["operation_phase"] = "planning"
            result = self.sync.sync_issue_projection(
                auth,
                run_dir,
                self.operation(
                    run_dir, operation_id="issue-m1-v2", action="update"
                ),
            )
            self.assertFalse(result["ok"])
            self.assertIn("issue_update_target_missing", result["errors"])

    def test_draft_update_preserves_create_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            actions = ["issue.create"]
            init_auth = authorization(external_actions=actions)
            auth = authorization(
                "goal-dispatch", "evidence.record", external_actions=actions
            )
            auth["operation_phase"] = "planning"
            self.init.initialize_run(init_auth, run_dir)
            create = self.operation(run_dir)
            intent = self.sync.sync_issue_projection(auth, run_dir, create)
            create["provider_result"] = {
                "operation_id": "issue-m1-v1",
                "desired_state_digest": intent["operation"]["desired_state_digest"],
                "provider_id": "issue-42",
                "state": "open",
            }
            self.assertTrue(
                self.sync.sync_issue_projection(auth, run_dir, create)["ok"]
            )
            draft_update = self.operation(
                run_dir,
                operation_id="issue-m1-v2",
                action="update",
                desired_state={"title": "M1 revised", "body": "Draft only"},
            )
            drafted = self.sync.sync_issue_projection(auth, run_dir, draft_update)
            self.assertEqual("draft", drafted["operation"]["status"])
            self.assertEqual("issue-42", drafted["operation"]["provider_id"])

            fresh_create = self.operation(
                run_dir, operation_id="issue-m1-v3", action="create"
            )
            replay = self.sync.sync_issue_projection(auth, run_dir, fresh_create)
            self.assertEqual("none", replay["provider_action"])
            self.assertEqual("issue-42", replay["operation"]["provider_id"])

    def test_unqualified_child_and_untrusted_provider_payload_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            auth = authorization(
                "goal-dispatch", "evidence.record", external_actions=["issue.create"]
            )
            auth["operation_phase"] = "planning"
            self.init.initialize_run(authorization(external_actions=["issue.create"]), run_dir)
            child = self.operation(
                run_dir,
                operation_id="issue-u1-v1",
                mapping_key="unit:u1",
                issue_kind="child",
                qualification={},
            )
            rejected = self.sync.sync_issue_projection(auth, run_dir, child)
            self.assertFalse(rejected["ok"])
            self.assertIn("child_issue_not_independently_qualifying", rejected["errors"])

            noncanonical = self.operation(
                run_dir, operation_id="issue-m1-other", mapping_key="primary:m1"
            )
            rejected = self.sync.sync_issue_projection(auth, run_dir, noncanonical)
            self.assertFalse(rejected["ok"])
            self.assertIn("primary_issue_mapping_invalid", rejected["errors"])

            first = self.sync.sync_issue_projection(auth, run_dir, self.operation(run_dir))
            forged = self.operation(
                run_dir,
                provider_result={
                    "operation_id": "issue-m1-v1",
                    "desired_state_digest": first["operation"]["desired_state_digest"],
                    "provider_id": "issue-42",
                    "api_token": "secret",
                },
            )
            bad_result = self.sync.sync_issue_projection(auth, run_dir, forged)
            self.assertFalse(bad_result["ok"])
            self.assertIn("provider_result_fields_invalid", bad_result["errors"])

            invalid_state = self.operation(
                run_dir,
                provider_result={
                    "operation_id": "issue-m1-v1",
                    "desired_state_digest": first["operation"][
                        "desired_state_digest"
                    ],
                    "provider_id": "issue-42",
                    "state": {"name": "open"},
                },
            )
            bad_state = self.sync.sync_issue_projection(auth, run_dir, invalid_state)
            self.assertFalse(bad_state["ok"])
            self.assertIn("provider_result_state_invalid", bad_state["errors"])


if __name__ == "__main__":
    unittest.main()
