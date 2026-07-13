from __future__ import annotations

import unittest

from support import load_script


class IndependentAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_script("check_independent_acceptance.py")

    def test_executor_cannot_accept_own_code_claim(self) -> None:
        result = self.module.check_acceptance(
            claim_type="code",
            executor_id="agent-1",
            verifier_id="agent-1",
            verifier_expert="architecture_and_code_review",
            accepted=True,
        )
        self.assertFalse(result["accepted"])

    def test_eligible_distinct_verifier_accepts(self) -> None:
        result = self.module.check_acceptance(
            claim_type="code",
            executor_id="agent-1",
            verifier_id="agent-2",
            verifier_expert="test_and_verification",
            accepted=True,
        )
        self.assertTrue(result["accepted"])

    def test_governed_acceptance_requires_nonempty_identities(self) -> None:
        result = self.module.check_acceptance(
            claim_type="security",
            executor_id="agent-1",
            verifier_id="",
            verifier_expert="security_and_risk",
            accepted=True,
        )
        self.assertFalse(result["accepted"])
        self.assertIn("verifier_id_missing", result["reasons"])

    def test_ineligible_verifier_is_rejected(self) -> None:
        result = self.module.check_acceptance(
            claim_type="security",
            executor_id="agent-1",
            verifier_id="agent-2",
            verifier_expert="documentation_and_communication",
            accepted=True,
        )
        self.assertFalse(result["accepted"])

    def test_low_risk_read_only_self_check_is_allowed(self) -> None:
        result = self.module.check_acceptance(
            claim_type="read_only",
            executor_id="agent-1",
            verifier_id="agent-1",
            verifier_expert="research_and_experiment",
            accepted=True,
        )
        self.assertTrue(result["accepted"])


if __name__ == "__main__":
    unittest.main()
