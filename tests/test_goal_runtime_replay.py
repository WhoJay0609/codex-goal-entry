from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def load_validator():
    path = ROOT / "scripts" / "validate_goal_runtime.py"
    spec = importlib.util.spec_from_file_location("goal_runtime_validator_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["goal_runtime_validator_tests"] = module
    spec.loader.exec_module(module)
    return module


class GoalRuntimeReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_validator()

    def test_engineering_trace_reaches_clean_closeout(self) -> None:
        result = self.validator.validate_trace_file(FIXTURES / "engineering_runtime_trace.json")
        self.assertEqual([], result["violations"])
        self.assertEqual("closed", result["terminal_state"])
        self.assertEqual(["m1", "m2"], result["accepted_milestones"])
        self.assertEqual([], result["unresolved_subagents"])

    def test_autoresearch_trace_preserves_results_and_claim_dispositions(self) -> None:
        result = self.validator.validate_trace_file(FIXTURES / "autoresearch_runtime_trace.json")
        self.assertEqual([], result["violations"])
        self.assertEqual("closed", result["terminal_state"])
        self.assertEqual(2, result["experiment_count"])
        self.assertEqual({"claim-1": "allowed", "claim-2": "qualified"}, result["claims"])

    def test_each_invalid_trace_fails_for_its_expected_invariant(self) -> None:
        cases = json.loads((FIXTURES / "invalid_runtime_traces.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(case=case["name"]):
                result = self.validator.validate_trace(case)
                joined = "\n".join(result["violations"])
                self.assertIn(case["expected_violation"], joined)

    def test_failed_milestone_can_retry_then_pass(self) -> None:
        trace = {
            "profile": "scientific_autoresearch",
            "events": [
                {"type": "goal_created", "goal_id": "g"},
                {"type": "roadmap_approved", "goal_id": "g"},
                {"type": "milestone_started", "milestone_id": "m", "dependencies": []},
                {"type": "milestone_evidence", "milestone_id": "m", "implementer": "i", "artifacts": ["v1"]},
                {"type": "milestone_verdict", "milestone_id": "m", "verifier": "v", "verdict": "failed"},
                {"type": "corrective_retry", "milestone_id": "m"},
                {"type": "milestone_evidence", "milestone_id": "m", "implementer": "i", "artifacts": ["v2"]},
                {"type": "milestone_verdict", "milestone_id": "m", "verifier": "v", "verdict": "passed"},
                {"type": "experiment_result", "experiment_id": "e", "integrity_status": "passed", "evidence_verdict": "supported", "result": "positive"},
                {"type": "claim_proposed", "claim_id": "c", "experiment_id": "e", "qualified": False},
                {"type": "goal_closed", "goal_id": "g"},
            ],
        }
        result = self.validator.validate_trace(trace)
        self.assertEqual([], result["violations"])
        self.assertEqual("closed", result["terminal_state"])

    def test_provider_invalidation_can_checkpoint_and_resume_compatibly(self) -> None:
        trace = {
            "profile": "complex_engineering",
            "events": [
                {"type": "goal_created", "goal_id": "g"},
                {"type": "roadmap_approved", "goal_id": "g"},
                {"type": "provider_attestation_invalidated", "provider_id": "p", "reason": "expired"},
                {"type": "provider_safe_checkpoint", "provider_id": "p", "checkpoint_ref": "cp-1"},
                {"type": "provider_attestation_renegotiated", "provider_id": "p", "compatible": True},
                {"type": "provider_phase_resumed", "provider_id": "p"},
                {"type": "milestone_started", "milestone_id": "m", "dependencies": []},
                {"type": "milestone_evidence", "milestone_id": "m", "implementer": "i", "artifacts": ["x"]},
                {"type": "milestone_verdict", "milestone_id": "m", "verifier": "v", "verdict": "passed"},
                {"type": "goal_closed", "goal_id": "g"},
            ],
        }
        result = self.validator.validate_trace(trace)
        self.assertEqual([], result["violations"])
        self.assertEqual("closed", result["terminal_state"])

    def test_incompatible_provider_renegotiation_preserves_pause(self) -> None:
        trace = {
            "profile": "complex_engineering",
            "events": [
                {"type": "goal_created", "goal_id": "g"},
                {"type": "roadmap_approved", "goal_id": "g"},
                {"type": "provider_attestation_invalidated", "provider_id": "p", "reason": "version"},
                {"type": "provider_safe_checkpoint", "provider_id": "p", "checkpoint_ref": "cp-1"},
                {"type": "provider_attestation_renegotiated", "provider_id": "p", "compatible": False},
                {"type": "branch_mutation", "branch": "b", "provider_id": "p"},
            ],
        }
        result = self.validator.validate_trace(trace)
        self.assertTrue(any("invalidated provider" in item for item in result["violations"]))


if __name__ == "__main__":
    unittest.main()
