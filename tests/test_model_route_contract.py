from __future__ import annotations

import json
import unittest

from support import ROOT, load_top_script


CASES = json.loads(
    (ROOT / "tests" / "fixtures" / "model_route_cases.json").read_text(
        encoding="utf-8"
    )
)


class ModelRouteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.validator = load_top_script("validate_model_route.py")

    def test_fixture_cases_define_model_owned_routing(self) -> None:
        for case in CASES:
            with self.subTest(case=case["name"]):
                result = self.validator.validate_model_route(case["route"])
                self.assertEqual(case["valid"], result["ok"])
                if "error" in case:
                    self.assertIn(case["error"], result["errors"])

    def test_named_skill_is_preserved_without_semantic_registry(self) -> None:
        case = next(item for item in CASES if item["name"] == "compound_named_skill")
        result = self.validator.validate_model_route(case["route"])
        self.assertEqual(
            "compound-engineering:ce-debug", result["route"]["preferred_skill"]
        )

    def test_contract_is_policy_data_not_a_phrase_classifier(self) -> None:
        contract = json.loads(
            (ROOT / "references" / "model_route_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            ["direct", "compound", "goal", "none"], contract["execution_levels"]
        )
        serialized = json.dumps(contract, ensure_ascii=False)
        self.assertNotIn("marker_groups", serialized)
        self.assertNotIn("regex", serialized.lower())

    def test_route_contract_documents_the_mechanical_envelope(self) -> None:
        contract = json.loads(
            (ROOT / "references" / "model_route_contract.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("authorization", contract["required_fields"])
        self.assertEqual(
            ["objective", "idempotency_key"], contract["goal_required_fields"]
        )
        self.assertIn("authorization", contract["inherited_context_fields"])
        self.assertEqual(
            ["authoritative_instruction"],
            contract["inherited_task_identity_fields"],
        )

    def test_short_reply_cannot_change_task_or_authorization(self) -> None:
        case = next(
            item
            for item in CASES
            if item["name"] == "short_reply_inherits_route_and_skill"
        )
        changed_task = json.loads(json.dumps(case["route"]))
        changed_task["objective"] = "Switch to a different project."
        result = self.validator.validate_model_route(changed_task)
        self.assertFalse(result["ok"])
        self.assertIn("inherited_objective_mismatch", result["errors"])

        widened = json.loads(json.dumps(case["route"]))
        widened["authorization"]["external_actions"] = ["pr.create"]
        result = self.validator.validate_model_route(widened)
        self.assertFalse(result["ok"])
        self.assertIn("inherited_authorization_mismatch", result["errors"])


if __name__ == "__main__":
    unittest.main()
