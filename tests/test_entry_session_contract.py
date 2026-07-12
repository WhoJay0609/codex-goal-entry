from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "references" / "entry_session_contract.json").read_text(encoding="utf-8"))


def load_resolver():
    path = ROOT / "scripts" / "resolve_goal_entry.py"
    spec = importlib.util.spec_from_file_location("entry_session_contract_tests", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["entry_session_contract_tests"] = module
    spec.loader.exec_module(module)
    return module


RESOLVER = load_resolver()


def resolve(request: str):
    return RESOLVER.resolve(SimpleNamespace(
        request=request,
        request_file=None,
        objective=None,
        objective_file=None,
        conversation_mode="default",
        active_goal_json=None,
        runtime_state_json=None,
        capabilities_json=None,
        readiness_status="passed",
    ))


class EntrySessionContractTests(unittest.TestCase):
    def test_contract_defines_exactly_two_ordered_passes(self) -> None:
        self.assertEqual(["semantic_pass", "authority_pass"], CONTRACT["passes"])

    def test_contract_keeps_legacy_projection_versions(self) -> None:
        self.assertEqual(2, CONTRACT["legacy_projections"]["top_level_version"])
        self.assertEqual(3, CONTRACT["legacy_projections"]["decision_contract_version"])
        decision = resolve("Please create a long-running Goal to implement this plan with tests")
        self.assertEqual(2, decision["version"])
        self.assertEqual(3, decision["decision_contract"]["version"])

    def test_contract_requires_external_authority_for_mutation(self) -> None:
        invariants = CONTRACT["invariants"]
        self.assertTrue(invariants["mutation_requires_resolved_semantics"])
        self.assertTrue(invariants["caller_state_is_advisory"])
        self.assertTrue(invariants["provider_declaration_is_not_attestation"])

    def test_each_acceptance_example_has_fixture_evidence(self) -> None:
        cases = json.loads((ROOT / "tests" / "fixtures" / "entry_session_cases.json").read_text(encoding="utf-8"))
        self.assertEqual({f"AE{index}" for index in range(1, 11)}, {case["ae_id"] for case in cases})
        for case in cases:
            with self.subTest(case=case["ae_id"]):
                decision = resolve(case["request"])
                if "expected_destination" in case:
                    self.assertEqual(case["expected_destination"], decision["execution_destination"])
                    self.assertNotIn("entry_session", decision)
                else:
                    session = decision["entry_session"]
                    self.assertEqual(case["expected_semantic"], session["semantic_pass"]["status"])
                    self.assertEqual(case["expected_authority"], session["authority_pass"]["status"])

    def test_goal_intent_precedence_is_enforced_by_the_resolver(self) -> None:
        self.assertEqual(tuple(CONTRACT["goal_intent_policy"]["precedence"]), RESOLVER.GOAL_INTENT_PRECEDENCE)
        self.assertEqual(RESOLVER.EXPECTED_GOAL_INTENT_PRECEDENCE, RESOLVER.GOAL_INTENT_PRECEDENCE)

    def test_resolver_emits_additive_entry_session_envelope(self) -> None:
        decision = resolve("Please create a long-running Goal to implement this plan with tests")
        session = decision["entry_session"]
        self.assertEqual(2, session["version"])
        self.assertIn(session["semantic_pass"]["status"], CONTRACT["semantic_states"])
        self.assertIn(session["authority_pass"]["status"], CONTRACT["authority_states"])

    def test_compound_result_omits_goal_only_envelopes(self) -> None:
        decision = resolve("Please implement this plan with tests")
        self.assertEqual("execute_compound", decision["request_mode"])
        self.assertEqual("compound_engineering", decision["execution_destination"])
        self.assertNotIn("decision_contract", decision)
        self.assertNotIn("entry_session", decision)


if __name__ == "__main__":
    unittest.main()
