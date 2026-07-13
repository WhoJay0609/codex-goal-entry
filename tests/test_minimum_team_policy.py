from __future__ import annotations

import importlib.util
import sys
import unittest

from support import ROOT


def load_team_script():
    path = ROOT / "skills" / "goal-team" / "scripts" / "select_goal_experts.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("select_goal_experts", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class MinimumTeamPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_team_script()

    def test_single_domain_low_risk_uses_one_primary(self) -> None:
        result = self.module.select_experts("implementation", [], "read_only")
        self.assertEqual(
            ["implementation"], [item["expert"] for item in result["team"]]
        )

    def test_cross_domain_adds_only_named_specialist(self) -> None:
        result = self.module.select_experts("implementation", ["frontend"], "read_only")
        self.assertEqual(
            ["implementation", "frontend_and_ui_engineering"],
            [item["expert"] for item in result["team"]],
        )

    def test_code_claim_adds_independent_verifier(self) -> None:
        result = self.module.select_experts("implementation", [], "code")
        self.assertEqual(2, len(result["team"]))
        self.assertEqual("primary", result["team"][0]["role"])
        self.assertEqual("independent_verifier", result["team"][1]["role"])
        self.assertNotEqual(
            result["team"][0]["instance_id"], result["team"][1]["instance_id"]
        )


if __name__ == "__main__":
    unittest.main()
