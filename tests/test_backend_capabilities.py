from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from support import authorization, load_script


class BackendCapabilityTests(unittest.TestCase):
    def test_initialize_and_record_goal_owned_evidence(self) -> None:
        init = load_script("init_goal_run.py")
        record = load_script("record_goal_evidence.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            created = init.initialize_run(authorization(), run_dir)
            self.assertTrue(created["ok"])
            manifest = json.loads((run_dir / "manifest.json").read_text())
            self.assertEqual("goal-run/v1", manifest["schema"])
            self.assertNotIn("mode", manifest)
            self.assertNotIn("superpowers", json.dumps(manifest).lower())

            auth = authorization("goal-team", "evidence.record")
            result = record.record_evidence(
                auth,
                run_dir,
                kind="expert_selected",
                status="completed",
                data={"expert": "implementation"},
            )
            self.assertTrue(result["ok"])
            row = json.loads((run_dir / "events.jsonl").read_text().splitlines()[0])
            self.assertEqual("goal-team", row["owner_skill"])
            self.assertEqual("completed", row["status"])

    def test_initialize_write_failure_does_not_leave_run_directory(self) -> None:
        init = load_script("init_goal_run.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            with mock.patch.object(
                init, "write_json_atomic", side_effect=OSError("disk full")
            ):
                with self.assertRaises(OSError):
                    init.initialize_run(authorization(), run_dir)
            self.assertFalse(run_dir.exists())

    def test_evidence_status_enum_is_enforced(self) -> None:
        init = load_script("init_goal_run.py")
        record = load_script("record_goal_evidence.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            self.assertTrue(init.initialize_run(authorization(), run_dir)["ok"])
            result = record.record_evidence(
                authorization("goal-team", "evidence.record"),
                run_dir,
                kind="bad",
                status="almost_done",
                data={},
            )
            self.assertFalse(result["ok"])

    def test_trace_validation_reports_distinct_statuses(self) -> None:
        init = load_script("init_goal_run.py")
        record = load_script("record_goal_evidence.py")
        validate = load_script("validate_goal_trace.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            init.initialize_run(authorization(), run_dir)
            self.assertEqual("missing", validate.validate_run(run_dir)["status"])
            record.record_evidence(
                authorization("goal-team", "evidence.record"),
                run_dir,
                kind="readiness",
                status="readiness_only",
                data={},
            )
            self.assertEqual("readiness_only", validate.validate_run(run_dir)["status"])
            record.record_evidence(
                authorization("goal-team", "evidence.record"),
                run_dir,
                kind="failure",
                status="failed",
                data={},
            )
            self.assertEqual("failed", validate.validate_run(run_dir)["status"])

    def test_governed_claim_requires_independent_acceptance(self) -> None:
        init = load_script("init_goal_run.py")
        record = load_script("record_goal_evidence.py")
        validate = load_script("validate_goal_trace.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            init.initialize_run(authorization(), run_dir)
            evidence_auth = authorization("goal-team", "evidence.record")
            record.record_evidence(
                evidence_auth,
                run_dir,
                kind="claim",
                status="completed",
                data={
                    "claim_id": "change-1",
                    "claim_type": "code",
                    "executor_id": "agent-1",
                },
            )
            missing = validate.validate_run(run_dir)
            self.assertFalse(missing["valid"])
            self.assertIn("independent_acceptance_missing:change-1", missing["errors"])
            record.record_evidence(
                evidence_auth,
                run_dir,
                kind="independent_acceptance",
                status="completed",
                data={
                    "claim_id": "change-1",
                    "claim_type": "code",
                    "executor_id": "agent-1",
                    "verifier_id": "agent-2",
                    "verifier_expert": "test_and_verification",
                    "accepted": True,
                },
            )
            self.assertTrue(validate.validate_run(run_dir)["valid"])

    def test_governed_claim_rejects_missing_verifier_identity(self) -> None:
        init = load_script("init_goal_run.py")
        record = load_script("record_goal_evidence.py")
        validate = load_script("validate_goal_trace.py")
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            init.initialize_run(authorization(), run_dir)
            evidence_auth = authorization("goal-team", "evidence.record")
            record.record_evidence(
                evidence_auth,
                run_dir,
                kind="claim",
                status="completed",
                data={
                    "claim_id": "change-2",
                    "claim_type": "code",
                    "executor_id": "agent-1",
                },
            )
            record.record_evidence(
                evidence_auth,
                run_dir,
                kind="independent_acceptance",
                status="completed",
                data={
                    "claim_id": "change-2",
                    "verifier_id": "",
                    "verifier_expert": "test_and_verification",
                    "accepted": True,
                },
            )
            result = validate.validate_run(run_dir)
            self.assertFalse(result["valid"])
            self.assertIn("independent_acceptance_missing:change-2", result["errors"])


if __name__ == "__main__":
    unittest.main()
