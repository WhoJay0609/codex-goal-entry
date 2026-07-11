from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "references" / "runtime_profiles.json"


class RuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_profiles_share_kernel_and_keep_distinct_progressions(self) -> None:
        profiles = self.contract["profiles"]
        self.assertEqual({"complex_engineering", "scientific_autoresearch"}, set(profiles))
        self.assertIn("integration", profiles["complex_engineering"]["stages"])
        self.assertIn("experiment_inner_loop", profiles["scientific_autoresearch"]["stages"])
        self.assertIn("independent_verifier_passed", self.contract["shared_kernel"]["milestone_acceptance_requires"])

    def test_retry_and_reclamation_defaults_are_positive_and_bounded(self) -> None:
        reclamation = self.contract["shared_kernel"]["reclamation"]
        self.assertEqual(120, reclamation["heartbeat_timeout_seconds"])
        self.assertEqual(900, reclamation["prolonged_blocking_seconds"])
        self.assertEqual(30, reclamation["graceful_reclamation_seconds"])
        self.assertEqual(2, self.contract["profiles"]["complex_engineering"]["max_corrective_retries"])
        self.assertEqual(1, self.contract["profiles"]["scientific_autoresearch"]["max_corrective_retries"])
        self.assertTrue(all(value > 0 for key, value in reclamation.items() if key.endswith("_seconds")))

    def test_claim_firewall_blocks_or_narrows_unsafe_claims(self) -> None:
        firewall = self.contract["shared_kernel"]["claim_firewall"]
        self.assertEqual("block", firewall["integrity_failed"])
        self.assertEqual("block", firewall["evidence_insufficient"])
        self.assertEqual("narrow_with_qualifiers", firewall["warning"])
        self.assertEqual("narrow_with_qualifiers", firewall["partial_support"])

    def test_goal_capabilities_are_never_owned_by_subagents(self) -> None:
        capabilities = self.contract["capabilities"]
        forbidden_owners = {"subagent", "runtime_subagent", "milestone_implementer"}
        self.assertTrue(capabilities)
        self.assertFalse(forbidden_owners.intersection(capabilities.values()))
        self.assertEqual("goal-close", capabilities["goal-close"])


if __name__ == "__main__":
    unittest.main()
