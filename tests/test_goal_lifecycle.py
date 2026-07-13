from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import authorization, load_script


def graph(status: str = "planned") -> dict:
    return {
        "version": 1,
        "milestones": [
            {
                "id": "m1",
                "title": "Deliver lifecycle",
                "acceptance_criteria": ["focused tests pass"],
                "status": status,
            }
        ],
        "work_units": [
            {
                "id": "u1",
                "milestone_id": "m1",
                "dependencies": [],
                "status": status,
                "risk": "high",
            }
        ],
    }


class GoalLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.init = load_script("init_goal_run.py")
        self.lifecycle = load_script("advance_goal_lifecycle.py")
        self.record = load_script("record_goal_evidence.py")
        self.sync = load_script("finalize_goal_sync.py")

    def record_blocked_sync(self, auth: dict, run_dir: Path) -> None:
        self.assertTrue(
            self.sync.record_goal_sync(
                auth,
                run_dir,
                phase="pre_update",
                goal_status="blocked",
                update_called=False,
            )["ok"]
        )
        self.assertTrue(
            self.sync.record_goal_sync(
                auth,
                run_dir,
                phase="post_update",
                goal_status="blocked",
                update_called=True,
            )["ok"]
        )

    def test_new_run_starts_planning_and_cannot_skip_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            created = self.init.initialize_run(authorization(), run_dir)
            self.assertEqual("planning", created["manifest"]["lifecycle_state"])
            invalid = self.lifecycle.advance_lifecycle(
                authorization("goal-close", "goal.sync"),
                run_dir,
                target_state="completed",
                expected_revision=0,
            )
            self.assertFalse(invalid["ok"])
            self.assertIn("lifecycle_transition_invalid", invalid["errors"])

    def test_blocked_transition_is_owned_by_goal_close(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            wrong_owner = authorization("goal-dispatch", "evidence.record")
            wrong_owner["operation_phase"] = "planning"
            denied = self.lifecycle.advance_lifecycle(
                wrong_owner, run_dir, target_state="blocked", expected_revision=0
            )
            self.assertFalse(denied["ok"])
            self.assertIn(
                "lifecycle_transition_capability_mismatch", denied["errors"]
            )

            close_auth = authorization("goal-close", "goal.sync")
            close_auth["operation_phase"] = "closeout"
            unsynchronized = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="blocked", expected_revision=0
            )
            self.assertFalse(unsynchronized["ok"])
            self.assertIn(
                "goal_sync_blocked_evidence_missing", unsynchronized["errors"]
            )
            self.record_blocked_sync(close_auth, run_dir)
            blocked = self.lifecycle.advance_lifecycle(
                close_auth, run_dir, target_state="blocked", expected_revision=0
            )
            self.assertTrue(blocked["ok"])
            self.assertEqual("blocked", blocked["manifest"]["lifecycle_state"])

    def test_lifecycle_retry_repairs_manifest_event_crash_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            close_auth = authorization("goal-close", "goal.sync")
            close_auth["operation_phase"] = "closeout"
            self.record_blocked_sync(close_auth, run_dir)
            with mock.patch.object(
                self.lifecycle,
                "append_goal_event",
                side_effect=OSError("simulated event append failure"),
            ):
                with self.assertRaises(OSError):
                    self.lifecycle.advance_lifecycle(
                        close_auth,
                        run_dir,
                        target_state="blocked",
                        expected_revision=0,
                    )
            manifest = self.lifecycle.load_manifest(run_dir)
            self.assertEqual("blocked", manifest["lifecycle_state"])
            repaired = self.lifecycle.advance_lifecycle(
                close_auth,
                run_dir,
                target_state="blocked",
                expected_revision=0,
            )
            self.assertTrue(repaired["ok"])
            self.assertTrue(repaired["replayed"])
            events = (run_dir / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("lifecycle_transition", events)

    def test_planning_requires_complete_graph_and_issue_projection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            auth["operation_phase"] = "planning"
            stored = self.lifecycle.store_task_graph(auth, run_dir, graph())
            self.assertTrue(stored["ok"])
            blocked = self.lifecycle.advance_lifecycle(
                auth, run_dir, target_state="active", expected_revision=0
            )
            self.assertFalse(blocked["ok"])
            self.assertIn("milestone_issue_projection_missing:m1", blocked["errors"])

    def test_lifecycle_compare_and_set_rejects_stale_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            manifest = json.loads((run_dir / "manifest.json").read_text())
            manifest["lifecycle_state"] = "active"
            manifest["lifecycle_revision"] = 1
            (run_dir / "manifest.json").write_text(json.dumps(manifest) + "\n")
            result = self.lifecycle.advance_lifecycle(
                authorization("goal-trace", "trace.validate"),
                run_dir,
                target_state="verifying",
                expected_revision=0,
            )
            self.assertFalse(result["ok"])
            self.assertIn("lifecycle_revision_conflict", result["errors"])

    def test_graph_rejects_cycles_invalid_risk_and_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            auth["operation_phase"] = "planning"
            invalid = graph()
            invalid["version"] = 2
            invalid["work_units"][0]["risk"] = "critical"
            invalid["work_units"][0]["dependencies"] = ["u1"]
            result = self.lifecycle.store_task_graph(auth, run_dir, invalid)
            self.assertFalse(result["ok"])
            self.assertIn("task_graph_version_invalid", result["errors"])
            self.assertIn("work_unit_dependencies_invalid:u1", result["errors"])
            self.assertIn("work_unit_risk_invalid:u1", result["errors"])

            cyclic = graph()
            cyclic["work_units"].append(
                {
                    "id": "u2",
                    "milestone_id": "m1",
                    "dependencies": ["u1"],
                    "status": "planned",
                    "risk": "low",
                }
            )
            cyclic["work_units"][0]["dependencies"] = ["u2"]
            result = self.lifecycle.store_task_graph(auth, run_dir, cyclic)
            self.assertFalse(result["ok"])
            self.assertIn("task_graph_dependency_cycle", result["errors"])

    def test_accepted_graph_rows_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            auth["operation_phase"] = "planning"
            accepted = graph("accepted")
            self.assertTrue(
                self.lifecycle.store_task_graph(auth, run_dir, accepted)["ok"]
            )
            changed = graph("accepted")
            changed["milestones"][0]["title"] = "Changed accepted milestone"
            result = self.lifecycle.store_task_graph(auth, run_dir, changed)
            self.assertFalse(result["ok"])
            self.assertIn("accepted_milestone_immutable:m1", result["errors"])

    def test_status_updates_respect_dependencies_and_milestone_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            auth["operation_phase"] = "planning"
            dependent = graph()
            dependent["work_units"].append(
                {
                    "id": "u2",
                    "milestone_id": "m1",
                    "dependencies": ["u1"],
                    "status": "planned",
                    "risk": "medium",
                }
            )
            self.assertTrue(
                self.lifecycle.store_task_graph(auth, run_dir, dependent)["ok"]
            )
            active_auth = authorization("goal-dispatch", "evidence.record")
            blocked = self.lifecycle.update_work_status(
                active_auth,
                run_dir,
                work_units={"u2": "active"},
                milestones={},
            )
            self.assertFalse(blocked["ok"])
            self.assertIn(
                "work_unit_dependency_not_accepted:u2:u1", blocked["errors"]
            )
            accepted = self.lifecycle.update_work_status(
                active_auth,
                run_dir,
                work_units={"u1": "accepted", "u2": "accepted"},
                milestones={"m1": "accepted"},
            )
            self.assertTrue(accepted["ok"])

    def test_verifying_requires_mechanical_independent_and_cleanup_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.init.initialize_run(authorization(), run_dir)
            plan_auth = authorization("goal-dispatch", "evidence.record")
            plan_auth["operation_phase"] = "planning"
            self.assertTrue(
                self.lifecycle.store_task_graph(
                    plan_auth, run_dir, graph("accepted")
                )["ok"]
            )
            manifest = json.loads((run_dir / "manifest.json").read_text())
            manifest["issue_projections"]["milestone:m1"] = {
                "status": "draft"
            }
            manifest["lifecycle_state"] = "active"
            manifest["lifecycle_revision"] = 1
            self.lifecycle.write_json_atomic(run_dir / "manifest.json", manifest)
            trace_auth = authorization("goal-trace", "trace.validate")
            trace_auth["operation_phase"] = "verifying"

            missing = self.lifecycle.advance_lifecycle(
                trace_auth, run_dir, target_state="verifying", expected_revision=1
            )
            self.assertFalse(missing["ok"])
            self.assertIn(
                "milestone_mechanical_evidence_missing:m1", missing["errors"]
            )
            self.assertIn("high_risk_claim_missing:u1", missing["errors"])

            evidence_auth = authorization("goal-team", "evidence.record")
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="milestone_acceptance",
                status="completed",
                data={
                    "milestone_id": "m1",
                    "mechanical_passed": True,
                    "evidence_refs": ["test://unit-suite"],
                },
            )
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="claim",
                status="completed",
                data={
                    "claim_id": "u1-code",
                    "work_unit_id": "u1",
                    "claim_type": "code",
                    "executor_id": "implementer-1",
                },
            )
            self.record.record_evidence(
                evidence_auth,
                run_dir,
                kind="independent_acceptance",
                status="completed",
                data={
                    "claim_id": "u1-code",
                    "verifier_id": "verifier-1",
                    "verifier_expert": "architecture_and_code_review",
                    "accepted": True,
                },
            )
            (run_dir / "runtime_handles.jsonl").write_text(
                json.dumps({"status": "active", "pid": 12345}) + "\n",
                encoding="utf-8",
            )
            unclean = self.lifecycle.advance_lifecycle(
                trace_auth, run_dir, target_state="verifying", expected_revision=1
            )
            self.assertFalse(unclean["ok"])
            self.assertIn(
                "runtime_cleanup_incomplete_before_verifying", unclean["errors"]
            )
            (run_dir / "cleanup.jsonl").write_text(
                json.dumps({"status": "completed"}) + "\n", encoding="utf-8"
            )
            verified = self.lifecycle.advance_lifecycle(
                trace_auth, run_dir, target_state="verifying", expected_revision=1
            )
            self.assertTrue(verified["ok"])


if __name__ == "__main__":
    unittest.main()
