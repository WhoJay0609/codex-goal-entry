from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from support import authorization, load_script


class GoalRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.init = load_script("init_goal_run.py")
        self.lifecycle = load_script("advance_goal_lifecycle.py")
        self.recovery = load_script("record_recovery_action.py")

    def initialize_retryable_run(self, run_dir: Path) -> dict:
        created = self.init.initialize_run(authorization(), run_dir)
        auth = authorization("goal-dispatch", "evidence.record")
        auth["operation_phase"] = "planning"
        graph = {
            "version": 1,
            "milestones": [
                {
                    "id": "m1",
                    "title": "Recover",
                    "acceptance_criteria": ["unit accepted"],
                    "status": "active",
                }
            ],
            "work_units": [
                {
                    "id": "u1",
                    "milestone_id": "m1",
                    "dependencies": [],
                    "status": "active",
                    "risk": "medium",
                }
            ],
        }
        self.assertTrue(self.lifecycle.store_task_graph(auth, run_dir, graph)["ok"])
        return created

    def test_retry_and_replan_budgets_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.initialize_retryable_run(run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            for expected in (1, 2):
                result = self.recovery.record_recovery_action(
                    auth,
                    run_dir,
                    operation_id=f"retry-{expected}",
                    unit_id="u1",
                    action="retry",
                    retry_limit=2,
                )
                self.assertTrue(result["ok"])
                self.assertEqual(expected, result["retry_count"])
                if expected == 1:
                    replay = self.recovery.record_recovery_action(
                        auth,
                        run_dir,
                        operation_id="retry-1",
                        unit_id="u1",
                        action="retry",
                        retry_limit=2,
                    )
                    self.assertTrue(replay["ok"])
                    self.assertTrue(replay["replayed"])
                    self.assertEqual(1, replay["retry_count"])
            exhausted = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="retry-3",
                unit_id="u1",
                action="retry",
                retry_limit=2,
            )
            self.assertFalse(exhausted["ok"])
            self.assertIn("retry_budget_exhausted", exhausted["errors"])

            first_replan = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="replan-1",
                unit_id="u1",
                action="replan",
                retry_limit=2,
            )
            self.assertTrue(first_replan["ok"])
            second_replan = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="replan-2",
                unit_id="u1",
                action="replan",
                retry_limit=2,
            )
            self.assertFalse(second_replan["ok"])
            self.assertIn("replan_budget_exhausted", second_replan["errors"])

    def test_retry_limit_cannot_be_widened_and_unit_must_be_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.initialize_retryable_run(run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            first = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="retry-1",
                unit_id="u1",
                action="retry",
                retry_limit=1,
            )
            self.assertTrue(first["ok"])
            widened = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="retry-widened",
                unit_id="u1",
                action="retry",
                retry_limit=2,
            )
            self.assertFalse(widened["ok"])
            self.assertIn("retry_limit_conflict", widened["errors"])
            unknown = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="retry-missing",
                unit_id="missing",
                action="retry",
                retry_limit=1,
            )
            self.assertFalse(unknown["ok"])
            self.assertIn("recovery_work_unit_unknown", unknown["errors"])
            over_cap = self.recovery.record_recovery_action(
                auth,
                run_dir,
                operation_id="retry-over-cap",
                unit_id="u1",
                action="retry",
                retry_limit=3,
            )
            self.assertFalse(over_cap["ok"])
            self.assertIn("retry_limit_invalid", over_cap["errors"])

    def test_recovery_operation_repairs_event_append_failure_without_recounting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.initialize_retryable_run(run_dir)
            auth = authorization("goal-dispatch", "evidence.record")
            arguments = {
                "operation_id": "retry-crash",
                "unit_id": "u1",
                "action": "retry",
                "retry_limit": 2,
            }
            with mock.patch.object(
                self.recovery,
                "append_goal_event",
                side_effect=OSError("simulated event append failure"),
            ):
                with self.assertRaises(OSError):
                    self.recovery.record_recovery_action(
                        auth, run_dir, **arguments
                    )
            replay = self.recovery.record_recovery_action(
                auth, run_dir, **arguments
            )
            self.assertTrue(replay["ok"])
            self.assertTrue(replay["replayed"])
            self.assertEqual(1, replay["retry_count"])


if __name__ == "__main__":
    unittest.main()
